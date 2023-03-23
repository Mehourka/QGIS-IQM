"""
Model exported as python.
Name : IQM indice F5
Group :
With QGIS : 32802
Author : Karim Mehour
"""

import numpy as np
import processing
from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
	QgsProcessing,
	QgsField,
	QgsFeatureSink,
	QgsVectorLayer,
	QgsFeatureRequest,
	QgsExpression,
	QgsExpressionContext,
	QgsProcessingAlgorithm,
	QgsExpressionContextUtils,
	QgsProcessingMultiStepFeedback,
	QgsProcessingParameterVectorLayer,
	QgsProcessingParameterFeatureSink,
	QgsProperty,
	QgsProject,
)
import sys

class IndiceF5(QgsProcessingAlgorithm):
	OUTPUT = 'OUTPUT'
	ID_FIELD = 'Id'
	TRANSECT_RATIO = 3

	def initAlgorithm(self, config=None):
		self.addParameter(QgsProcessingParameterVectorLayer('bande_riveraine_polly', 'Bande_riveraine_polly', types=[QgsProcessing.TypeVectorPolygon], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('ptref_widths', 'PtRef_widths', types=[QgsProcessing.TypeVectorPoint], defaultValue=None))
		self.addParameter(QgsProcessingParameterVectorLayer('rivnet', 'RivNet', types=[QgsProcessing.TypeVectorLine], defaultValue=None))
		self.addParameter(QgsProcessingParameterFeatureSink(self.OUTPUT, self.OUTPUT, type=QgsProcessing.TypeVectorAnyGeometry, createByDefault=True, supportsAppend=True, defaultValue=None))

	def processAlgorithm(self, parameters, context, model_feedback):

		# Use a multi-step feedback
		feedback = QgsProcessingMultiStepFeedback(3, model_feedback)

		# Define source stream net
		source = self.parameterAsSource(parameters, 'rivnet', context)

		# Define Sink
		sink_fields = source.fields()
		sink_fields.append(QgsField("Indice F5", QVariant.Int))
		(sink, dest_id) = self.parameterAsSink(
			parameters,
			self.OUTPUT,
			context,
			sink_fields,
			source.wkbType(),
			source.sourceCrs()
		)

		print(sys.path)

		# feature count for feedback
		feature_count = source.featureCount()
		fid_idx = source.fields().indexFromName(self.ID_FIELD)

		for segment in source.getFeatures():
			# gen transects, and analyse intersection with 'Bande riv'
			points_along_line = pointsAlongLines(segment, source, context, feedback)
			normals = gen_split_normals(points_along_line, parameters, context, feedback)
			br_widths_arr = get_bandriv_width_arr(normals, parameters)

			# Compute the IQM Score
			indiceF5 = computeF5(br_widths_arr)

			# Write Index to layer
			segment.setAttributes(
				segment.attributes() + [indiceF5]
			)
			# Add a feature to sink
			sink.addFeature(segment, QgsFeatureSink.FastInsert)


		return {self.OUTPUT : dest_id}

	def tr(self, string):
		return QCoreApplication.translate('Processing', string)

	def createInstance(self):
		return IndiceF5()

	def name(self):
		return 'indicef5'

	def displayName(self):
		return self.tr('Indice F5')

	def group(self):
		return self.tr('IQM')

	def groupId(self):
		return self.tr('iqm')

	def shortHelpString(self):
		return self.tr("Clacule l'indice F5 de l'IQM (sinuosité)")

	def flags(self):
		return QgsProcessingAlgorithm.FlagNoThreading

def pointsAlongLines(feature, source, context, feedback=None, output=QgsProcessing.TEMPORARY_OUTPUT):
	NUMBER = 50

	feature = source.materialize(QgsFeatureRequest().setFilterFids([feature.id()]))

	# Points along lines
	alg_params = {
		'DISTANCE': QgsProperty.fromExpression(f"length(@geometry) / {NUMBER}"),
		'END_OFFSET': 0,
		'INPUT': feature,
		'START_OFFSET': 0,
		'OUTPUT': output,
	}
	result_id = processing.run('native:pointsalonglines', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
	return context.takeResultLayer(result_id)

def gen_split_normals(points, parameters, context, feedback=None, output=QgsProcessing.TEMPORARY_OUTPUT,):
	# Geometry by expression
	TRANSECT_RATIO = 1.5
	TRANSECT_FLAT = 30

	side_normals = []
	for angle in [90, -90]:
		alg_params = {
			'EXPRESSION':f"""with_variable(
				'len',overlay_nearest('{parameters['ptref_widths']}',Largeur_mod)[0] * {0.5 + TRANSECT_RATIO} + {TRANSECT_FLAT},
				make_line(@geometry,project(@geometry,@len,radians(\"angle\" + {angle}))))
			""",
			'INPUT': points,
			'OUTPUT_GEOMETRY': 1,  # Line
			'WITH_M': False,
			'WITH_Z': False,
			'OUTPUT': output
		}
		side_normals.append(processing.run('native:geometrybyexpression', alg_params, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT'])
	res_id = processing.run("native:mergevectorlayers", {'LAYERS':side_normals,'CRS':None,'OUTPUT':'TEMPORARY_OUTPUT'}, context=context, feedback=feedback, is_child_algorithm=True)['OUTPUT']
	return context.takeResultLayer(res_id)

def evaluate_expression(expression_str, vlayer, feature=None ):
	expression = QgsExpression(expression_str)
	context = QgsExpressionContext()
	if feature:
		context.setFeature(feature)
	scopes = QgsExpressionContextUtils.globalProjectLayerScopes(vlayer)
	context.appendScopes(scopes)
	res = expression.evaluate(context)
	return res

def get_bandriv_width_arr(vlayer, parameters):
	#Evaluating intersection distance
	intersection_expr = f"""
		max(
			0,
			length(
				segments_to_lines(
					intersection(
						@geometry,collect_geometries(
							overlay_intersects('{parameters['bande_riveraine_polly']}',@geometry)
						)
					)
				)
			)
		)
	"""
	expr = QgsExpression(f"array_agg({intersection_expr})")
	result = np.array(evaluate_expression(expr, vlayer))
	return result

def computeF5(br_widths_arr):
	# Compute Iqm from sequence continuity
	if (np.mean(br_widths_arr >= 30)  >= 0.9):
		return 0
	if (np.mean(br_widths_arr >= 30) >= 0.66):
		return 1
	if (np.mean(br_widths_arr >= 15) >= 0.66):
		return 2
	if (np.mean(br_widths_arr >= 30) >= 0.33):
		return 2
	if (np.mean(br_widths_arr >= 15) >= 0.33):
		return 3
	return 4