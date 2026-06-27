import 'package:flutter/material.dart';

import '../models/audio_metrics.dart';
import '../services/api_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_ui.dart';

class EcologyScreen extends StatefulWidget {
  final String baseUrl;

  const EcologyScreen({super.key, required this.baseUrl});

  @override
  State<EcologyScreen> createState() => _EcologyScreenState();
}

class _EcologyScreenState extends State<EcologyScreen> {
  late final ApiService api;

  late Future<List<AudioMetric>> _metricsFuture;
  late Future<Map<String, dynamic>> _biodiversityFuture;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _loadData();
  }

  void _loadData() {
    _metricsFuture = api.getAudioMetrics();
    _biodiversityFuture = api.getBiodiversityAnalytics();
  }

  Future<void> _refresh() async {
    setState(() {
      _loadData();
    });

    await Future.wait([_metricsFuture, _biodiversityFuture]);
  }

  Widget _buildBiodiversityGrid(Map<String, dynamic> data) {
    if (data.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay datos de biodiversidad disponibles.'),
      );
    }

    return AppMetricGrid(
      children: data.entries.map((entry) {
        return AppMetricCard(
          icon: Icons.eco,
          label: prettyLabel(entry.key),
          value: formatValue(entry.value),
        );
      }).toList(),
    );
  }

  Widget _buildLatestMetricGrid(AudioMetric? metric) {
    if (metric == null) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay metricas acusticas disponibles.'),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AppDataPanel(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              const Icon(Icons.graphic_eq),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Ultima muestra: ${formatTimestamp(metric.timestamp)}',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ),
        AppMetricGrid(
          children: [
            AppMetricCard(
              icon: Icons.speed,
              label: 'RMS',
              value: formatValue(metric.rms),
            ),
            AppMetricCard(
              icon: Icons.show_chart,
              label: 'ACI',
              value: formatValue(metric.aci),
            ),
            AppMetricCard(
              icon: Icons.bar_chart,
              label: 'ADI',
              value: formatValue(metric.adi),
            ),
            AppMetricCard(
              icon: Icons.area_chart,
              label: 'AEI',
              value: formatValue(metric.aei),
            ),
            AppMetricCard(
              icon: Icons.biotech,
              label: 'BIO',
              value: formatValue(metric.bio),
            ),
            AppMetricCard(
              icon: Icons.nature,
              label: 'NDSI',
              value: formatValue(metric.ndsi),
            ),
            AppMetricCard(
              icon: Icons.multiline_chart,
              label: 'HT',
              value: formatValue(metric.ht),
            ),
            AppMetricCard(
              icon: Icons.stacked_line_chart,
              label: 'HF',
              value: formatValue(metric.hf),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildRecentMetricsList(List<AudioMetric> metrics) {
    if (metrics.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay metricas acusticas registradas.'),
      );
    }

    final recent = metrics.take(6).toList();

    return AppDataPanel(
      child: Column(
        children: [
          for (var i = 0; i < recent.length; i++) ...[
            if (i > 0) const Divider(height: 1),
            ListTile(
              leading: const Icon(Icons.audiotrack),
              title: Text(formatTimestamp(recent[i].timestamp)),
              subtitle: Text(recent[i].filename ?? 'Sin archivo asociado'),
              trailing: AppStatusPill(
                text: 'NDSI ${formatValue(recent[i].ndsi)}',
                icon: Icons.nature,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildInterpretation(
    AudioMetric? latestMetric,
    Map<String, dynamic> biodiversity,
  ) {
    final notes = <String>[];
    final ndsi = latestMetric?.ndsi;
    final richnessRaw = biodiversity['riqueza'];
    final shannonRaw = biodiversity['shannon'];
    final quality = biodiversity['calidad']?.toString();

    if (ndsi != null && ndsi < 0) {
      notes.add(
        'NDSI negativo: posible predominio de ruido antropogenico frente a biofonia.',
      );
    }

    final richness = richnessRaw is num
        ? richnessRaw
        : num.tryParse(richnessRaw?.toString() ?? '');
    if (richness != null && richness <= 3) {
      notes.add(
        'Riqueza baja: se han detectado pocas especies en el periodo analizado.',
      );
    }

    final shannon = shannonRaw is num
        ? shannonRaw
        : num.tryParse(shannonRaw?.toString() ?? '');
    if (shannon != null && shannon < 1) {
      notes.add(
        'Shannon bajo: la comunidad acustica detectada presenta baja diversidad relativa.',
      );
    }

    if (quality != null && quality.trim().isNotEmpty) {
      notes.add('Calidad ecologica reportada: $quality.');
    }

    if (notes.isEmpty) {
      notes.add(
        'Sin alertas interpretativas claras con los datos disponibles.',
      );
    }

    return AppDataPanel(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Diagnostico', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final note in notes)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.insights, size: 18),
                  const SizedBox(width: 8),
                  Expanded(child: Text(note)),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildContent(
    List<AudioMetric> metrics,
    Map<String, dynamic> biodiversity,
  ) {
    final latestMetric = metrics.isNotEmpty ? metrics.first : null;

    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.eco,
          title: 'Analisis bioacustico',
          subtitle: 'Lectura ecologica y acustica del paisaje sonoro.',
          trailing: AppStatusPill(
            text: metrics.length.toString(),
            icon: Icons.graphic_eq,
          ),
        ),
        const AppSectionTitle(
          title: 'Biodiversidad',
          subtitle: 'Indices ecologicos calculados sobre las detecciones.',
        ),
        _buildBiodiversityGrid(biodiversity),
        const AppSectionTitle(
          title: 'Interpretacion',
          subtitle: 'Lectura automatica basica de los indicadores.',
        ),
        _buildInterpretation(latestMetric, biodiversity),
        const AppSectionTitle(
          title: 'Indices acusticos',
          subtitle: 'Ultima muestra de metricas bioacusticas.',
        ),
        _buildLatestMetricGrid(latestMetric),
        const AppSectionTitle(title: 'Registros recientes'),
        _buildRecentMetricsList(metrics),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<List<dynamic>>(
        future: Future.wait([_metricsFuture, _biodiversityFuture]),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const AppPage(
              children: [
                SizedBox(height: 220),
                Center(child: CircularProgressIndicator()),
              ],
            );
          }

          if (snapshot.hasError) {
            return AppPage(
              children: [
                AppDataPanel(
                  padding: const EdgeInsets.all(16),
                  child: Text('Error cargando analisis: ${snapshot.error}'),
                ),
              ],
            );
          }

          final metrics = snapshot.data![0] as List<AudioMetric>;
          final biodiversity = snapshot.data![1] as Map<String, dynamic>;

          return _buildContent(metrics, biodiversity);
        },
      ),
    );
  }
}