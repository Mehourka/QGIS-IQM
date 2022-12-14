"""
Model exported as python.
Name : IndiceA2
Group : 
With QGIS : 32601
"""
from tempfile import NamedTemporaryFile as Ntf
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsProcessing,
                       QgsField,
                       QgsFeatureSink,
                       QgsVectorLayer,
                       )
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterVectorLayer
from qgis.core import QgsProcessingParameterFeatureSink
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import QgsCoordinateReferenceSystem
import processing


class IndiceA2(QgsProcessingAlgorithm):
    ID_FIELD = 'Id'
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('stream_network', 'Cours d\'eau', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('dams', 'Dams', defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('sink', 'Output', defaultValue=None))
        
        

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(11, model_feedback)
        results = {}
        outputs = {}

        # Create temporary file locations
        tmp = {
            'd8': Ntf(suffix="d8.tif"),
            'mainWatershed' : Ntf(suffix="watershed.tif"),
            'subWatershed' : Ntf(suffix="sub-watershed.tif"),
        }

        # Define source stream net
        source = self.parameterAsSource(parameters, 'stream_network', context)

        # Define Sink fields
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice A2", QVariant.Int))

        # Define sink
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            'sink',
            context,
            sink_fields,
            source.wkbType(),
            source.sourceCrs()
        )

        # WBT : Create D8 from dem
        # FillBurn
        alg_params = {
            'dem': parameters['dem'],
            'streams': parameters['stream_network'],
            'output': tmp['d8'].name
        }
        outputs['Fillburn'] = processing.run(
            'wbt:FillBurn', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # FillDepressions
        alg_params = {
            'dem': outputs['Fillburn']['output'],
            'fix_flats': True,
            'flat_increment': None,
            'max_depth': None,
            'output': tmp['d8'].name
        }
        outputs['Filldepressions'] = processing.run(
            'wbt:FillDepressions', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}
            
        # BreachDepressions
        alg_params = {
            'dem': outputs['Fillburn']['output'],
            'fill_pits': True,
            'flat_increment': 0.001,
            'max_depth': None,
            'max_length': None,
            'output': tmp['d8'].name
        }
        outputs['Breachdepressions'] = processing.run(
            'wbt:BreachDepressions', alg_params, context=context, feedback=feedback, is_child_algorithm=False)
    
        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # D8Pointer
        alg_params = {
            'dem': outputs['Breachdepressions']['output'],
            'esri_pntr': False,
            'output': tmp['d8'].name
        }
        outputs['D8pointer'] = processing.run(
            'wbt:D8Pointer', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # Snap dams to river network
        # Snapped Dams
        alg_params = {
            'BEHAVIOR': 1,  # Prefer closest point, insert extra vertices where required
            'INPUT': parameters['dams'],
            'REFERENCE_LAYER': parameters['stream_network'],
            'TOLERANCE': 75,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['SnappedDams'] = processing.run('native:snapgeometries', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
       
        
        # Extract specific vertex
        # TODO : try and remove is_child_algorithm
        alg_params = {
            'INPUT': parameters['stream_network'],
            'VERTICES': '-2',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExtractSpecificVertex'] = processing.run(
            'native:extractspecificvertices', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}

        ############ LOOP GOES HERE ############

        vertices = outputs['ExtractSpecificVertex']['OUTPUT']

        features = [f for f in source.getFeatures()]
        feature_count = source.featureCount()
        id_field = self.ID_FIELD
        
        for current, feature in enumerate(features):
            fid = feature[id_field]
            # For each segment
            # Compute waterhed
            if feedback.isCanceled():
                return {}

            # Extract By Attribute
            alg_params = {
                'FIELD': id_field,
                'INPUT': outputs['ExtractSpecificVertex']['OUTPUT'],
                'OPERATOR': 0,  # =
                'VALUE': str(fid),
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }

            outputs['single_point'] = processing.run(
                'native:extractbyattribute', alg_params, context=context, feedback=feedback)

            # Watershed
            alg_params = {
                'd8_pntr': tmp['d8'].name,
                'esri_pntr': False,
                'pour_pts': outputs['single_point']['OUTPUT'],
                'output': tmp['mainWatershed'].name
            }
            outputs['mainWatershed'] = processing.run(
                'wbt:Watershed', alg_params, context=context, feedback=feedback)

            # Polygonize (raster to vector)
            alg_params = {
                'BAND': 1,
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA': '',
                'FIELD': 'DN',
                'INPUT': outputs['mainWatershed']['output'],
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['mainWatershedPoly'] = processing.run(
                'gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=False)
            
            # Compute watershed total area
            mainWatershedPoly = QgsVectorLayer(
                outputs['mainWatershedPoly']['OUTPUT'], 'vector main watershed', 'ogr')
            main_area = sum([feat.geometry().area()
                           for feat in mainWatershedPoly.getFeatures()])

            # Clip Dams
            alg_params = {
                'INPUT': outputs['SnappedDams']['OUTPUT'],
                'INTERSECT': outputs['mainWatershedPoly']['OUTPUT'],
                'PREDICATE': [6],  # are within
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['ClipDams'] = processing.run('native:extractbylocation', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

             # Watershed
            alg_params = {
                'd8_pntr': outputs['D8pointer']['output'],
                'esri_pntr': False,
                'pour_pts': outputs['ClipDams']['OUTPUT'],
                'output': tmp['subWatershed'].name
            }
            outputs['subWatershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

            feedback.setCurrentStep(10)
            if feedback.isCanceled():
                return {}

            # Vectorized Sub-watersheds
            alg_params = {
                'BAND': 1,
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA': '',
                'FIELD': 'DN',
                'INPUT': outputs['subWatershed']['output'],
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['subWatershedPoly'] = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
            
            # Compute watershed total area
            subWatershedPoly = QgsVectorLayer(
                outputs['subWatershedPoly']['OUTPUT'], 'vector sub watershed', 'ogr')
            sub_area = sum([feat.geometry().area()
                           for feat in subWatershedPoly.getFeatures()])
            
            indiceA2 = 0

            if main_area != 0 and sub_area != 0:
                # get dams sub watersheds area ration
                ratio = sub_area / main_area
                if ratio < 0.05:
                    indiceA2 = 0
                elif 0.05 <= ratio < 0.33:
                    indiceA2 = 2
                elif 0.33 <= ratio < 0.66:
                    indiceA2 = 3
                elif 0.66 <= ratio:
                    indiceA2 = 4
                

            # Add forest area to new featuer
            feature.setAttributes(
                feature.attributes() + [indiceA2]
            )

            # Add modifed feature to sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)

            print(f'{current}/{feature_count}')

        # Clear temporary files
        for tempfile in tmp.values():
            tempfile.close()

        return {'IQM': dest_id}

    def name(self):
        return 'Indice A2'

    def displayName(self):
        return 'Indice A2'

    def group(self):
        return 'IQM'

    def groupId(self):
        return 'iqm'

    def createInstance(self):
        return IndiceA2()
