"""
Model exported as python.
Name : Indice A1
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


class IndiceA1(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('dem', 'DEM', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('landuse', 'Utilisation du territoir', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorLayer('stream_network', 'Cours d\'eau', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
        self.addParameter(QgsProcessingParameterFeatureSink('sink', 'Output', defaultValue=None))
        #self.addParameter(QgsProcessingParameterNumber('outlet_fid', 'outlet_FID', type=QgsProcessingParameterNumber.Integer, minValue=0, defaultValue=None))
        #self.addParameter(QgsProcessingParameterFeatureSink('Report', 'report', optional=True, type=QgsProcessing.TypeVector, createByDefault=False, defaultValue=None))
        #self.addParameter(QgsProcessingParameterRasterDestination('Tmpreclassifiedtif', '/tmp/reclassified.tif', createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(11, model_feedback)
        results = {}
        outputs = {}
        
        # Create temporary file locations
        tmp = {}
        
        # Create tmp File #1 for D8 Creation
        tmp['d8'] = Ntf(suffix="d8.tif")
        tmp['watershed'] = Ntf(suffix="watershed.tif")
        
        # Define source stream net 
        source = self.parameterAsSource(parameters, 'stream_network', context)
        
        # Define Sink fields
        sink_fields = source.fields()
        sink_fields.append(QgsField("Indice A1", QVariant.Int))
        
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
        outputs['Fillburn'] = processing.run('wbt:FillBurn', alg_params, context=context, feedback=feedback, is_child_algorithm=False)
        
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
        outputs['Filldepressions'] = processing.run('wbt:FillDepressions', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # BreachDepressionsLeastCost
        alg_params = {
            'dem': outputs['Fillburn']['output'],
            'dist': 10,
            'fill': True,
            'flat_increment': None,
            'max_cost': None,
            'min_dist': False,
            'output': tmp['d8'].name
        }
        outputs['Breachdepressionsleastcost'] = processing.run('wbt:BreachDepressionsLeastCost', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # D8Pointer
        alg_params = {
            'dem': outputs['Breachdepressionsleastcost']['output'],
            'esri_pntr': False,
            'output': tmp['d8'].name
        }
        outputs['D8pointer'] = processing.run('wbt:D8Pointer', alg_params, context=context, feedback=feedback, is_child_algorithm=False)

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}
        
        # D8 Created #
        
        
        # Reclassify land use
        alg_params = {
            'DATA_TYPE': 0,  # Byte
            'INPUT_RASTER': parameters['landuse'],
            'NODATA_FOR_MISSING': True,
            'NO_DATA': 0,
            'RANGE_BOUNDARIES': 2,  # min <= value <= max
            'RASTER_BAND': 1,
            'TABLE': [ 
                '50','56','1','210','235','1','501','735','1','101','199','2',
                '2050','2056','1','2210','2235','1','2501','2735','1','2101','2199','2',
                '4050','4056','1','4210','4235','1','4501','4735','1','4101','4199','2',
                '5050','5056','1','5210','5235','1','5501','5735','1','5101','5199','2',
                '6050','6056','1','6210','6235','1','6501','6735','1','6101','6199','2',
                '7050','7056','1','7210','7235','1','7501','7735','1','7101','7199','2',
                '8050','8056','1','8210','8235','1','8501','8735','1','8101','8199','2'
                ],

            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ReducedLanduse'] = processing.run('native:reclassifybytable', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        
        # Extract specific vertex
        # TODO : try and remove is_child_algorithm
        alg_params = {
            'INPUT': parameters['stream_network'],
            'VERTICES': '-2',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['ExtractSpecificVertex'] = processing.run('native:extractspecificvertices', alg_params, context=context, feedback=feedback, is_child_algorithm=False)
        
        feedback.setCurrentStep(5)
        if feedback.isCanceled():
            return {}
        
        ############ LOOP GOES HERE ############
        # Looping through vertices
        #fid_index = outputs['ExtractSpecificVertex']['OUTPUT'].fields().indexFromName('fid')
        #fid_ids = outputs['ExtractSpecificVertex']['OUTPUT'].uniqueValues(fid_index)
        
        vertices = outputs['ExtractSpecificVertex']['OUTPUT']
        
        #for fid in list(fid_ids)[189:192]:
        features = [f for f in source.getFeatures()]
        feature_count = source.featureCount()
        id_field = 'Id'
        for current, feature in enumerate(features):
            fid = feature[id_field]
            # For each pour point
            # Compute the percentage of forests and agriculture lands in the draining area
            # Then compute index_A1 and add it in a new field to the river network
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
            
            outputs['single_point']= processing.run('native:extractbyattribute', alg_params, context=context, feedback=feedback)
            
            # Watershed
            alg_params = {
                'd8_pntr': tmp['d8'].name,
                'esri_pntr': False,
                'pour_pts': outputs['single_point']['OUTPUT'],
                'output': tmp['watershed'].name
            }
            outputs['Watershed'] = processing.run('wbt:Watershed', alg_params, context=context, feedback=feedback)        
            
            # Polygonize (raster to vector)
            alg_params = {
                'BAND': 1,
                'EIGHT_CONNECTEDNESS': False,
                'EXTRA': '',
                'FIELD': 'DN',
                'INPUT': outputs['Watershed']['output'],
                'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['PolygonizeRasterToVector'] = processing.run('gdal:polygonize', alg_params, context=context, feedback=feedback, is_child_algorithm=False)
            
            # Drain_area Land_use
            alg_params = {
                'ALPHA_BAND': False,
                'CROP_TO_CUTLINE': True,
                'DATA_TYPE': 0,  # Use Input Layer Data Type
                'EXTRA': '',
                'INPUT': outputs['ReducedLanduse']['OUTPUT'],
                'KEEP_RESOLUTION': True,
                'MASK': outputs['PolygonizeRasterToVector']['OUTPUT'],
                'MULTITHREADING': False,
                'NODATA': None,
                'OPTIONS': '',
                'SET_RESOLUTION': False,
                'SOURCE_CRS': QgsCoordinateReferenceSystem('EPSG:32198'),
                'TARGET_CRS': 'ProjectCrs',
                'TARGET_EXTENT': None,
                'X_RESOLUTION': None,
                'Y_RESOLUTION': None,
                'OUTPUT': f"tmp/aire_drainage_landuse_allclasses/landuse_drainage_{fid}.tif" #QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['Drain_areaLand_use'] = processing.run('gdal:cliprasterbymasklayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

            # Landuse unique values report
            alg_params = {
                'BAND': 1,
                'INPUT': outputs['Drain_areaLand_use']['OUTPUT'],
                'OUTPUT_TABLE': QgsProcessing.TEMPORARY_OUTPUT
            }
            outputs['LanduseUniqueValuesReport'] = processing.run('native:rasterlayeruniquevaluesreport', alg_params, context=context, feedback=feedback, is_child_algorithm=False)
            
            # Compute watershed total area
            watershed_poly = QgsVectorLayer(outputs['PolygonizeRasterToVector']['OUTPUT'], 'poly', 'ogr')
            tot_area = sum([feat.geometry().area() for feat in watershed_poly.getFeatures()])
            
                

            # Here we compute forest and agri area, the add to new feture
            
            table = outputs['LanduseUniqueValuesReport']['OUTPUT_TABLE']
            
            
            forest_area = 0
            agri_area = 0
            
            if tot_area != 0:
                # Get forest and agri areas
                for feat in table.getFeatures():
                    if feat[0] == 1:
                        forest_area = feat[2]/tot_area
                    elif feat[0] == 2:
                        agri_area = feat[2]/tot_area
                
                
                # Assigne index A1
                if forest_area >= 0.9:
                    indiceA1 = 0
                elif forest_area >= 0.66 and agri_area <= 0.33:
                    indiceA1 = 1
                elif forest_area <= 0.66 and agri_area >= 0.33:
                    indiceA1 = 2
                elif forest_area <= 0.33:
                    indiceA1 = 4
                elif forest_area <= 0.1:
                    indiceA1 = 5
                else:
                    indiceA1 = 5
            else:
                # TODO : replace by null value
                indiceA1 = 5
            
            # Add forest area to new featuer
            feature.setAttributes(
                    feature.attributes() + [indiceA1]
            )
            
            # Add modifed feature to sink
            sink.addFeature(feature, QgsFeatureSink.FastInsert)
            
            print(f'{current}/{feature_count}')
            
        # Clear temporary files
        for tempfile in tmp.values():
            tempfile.close()
        
        return {'IQM': dest_id}

    def name(self):
        return 'Indice A1'

    def displayName(self):
        return 'Indice A1'

    def group(self):
        return 'IQM'

    def groupId(self):
        return 'iqm'

    def createInstance(self):
        return IndiceA1()
