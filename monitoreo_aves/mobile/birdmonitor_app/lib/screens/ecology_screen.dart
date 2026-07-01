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

  num? _readNumber(Map<String, dynamic> data, String key) {
    final value = data[key];
    if (value is num) return value;
    return num.tryParse(value?.toString() ?? '');
  }

  double? _boundedProgress(num? value) {
    if (value == null) return null;
    final absolute = value.abs().toDouble();
    if (absolute == 0) return 0;
    return (absolute / (absolute + 1)).clamp(0, 1).toDouble();
  }

  double? _rangeProgress(num? value, double min, double max) {
    if (value == null || max <= min) return null;
    return ((value - min) / (max - min)).clamp(0, 1).toDouble();
  }

  String _bioacousticLevel(AudioMetric? metric) {
    final ndsi = metric?.ndsi;
    if (metric == null || ndsi == null) return 'Sin lectura acustica';
    if (ndsi >= 0.35) return 'Biofonia dominante';
    if (ndsi >= 0.08) return 'Biofonia presente';
    if (ndsi > -0.20) return 'Paisaje mixto';
    return 'Ruido dominante';
  }

  String _bioacousticDescription(AudioMetric? metric) {
    final ndsi = metric?.ndsi;
    if (metric == null) {
      return 'Todavia no hay muestras acusticas para interpretar.';
    }
    if (ndsi == null) {
      return 'La ultima muestra no incluye NDSI, pero conserva el resto de indices.';
    }
    if (ndsi >= 0.35) {
      return 'Predominan sonidos biologicos frente al ruido de fondo.';
    }
    if (ndsi >= 0.08) {
      return 'Hay actividad biologica reconocible en el paisaje sonoro.';
    }
    if (ndsi > -0.20) {
      return 'La muestra mezcla biofonia, ambiente y posible ruido antropico.';
    }
    return 'El ruido pesa mas que la biofonia en la muestra reciente.';
  }

  Widget _buildMetricLine({
    required IconData icon,
    required String label,
    required String value,
    required String description,
    double? progress,
    String? startLabel,
    String? endLabel,
  }) {
    final color = Theme.of(context).colorScheme.primary;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        label,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ),
                    Text(value, style: Theme.of(context).textTheme.titleMedium),
                  ],
                ),
                const SizedBox(height: 4),
                Text(description, style: Theme.of(context).textTheme.bodySmall),
                if (progress != null) ...[
                  const SizedBox(height: 8),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(999),
                    child: LinearProgressIndicator(
                      value: progress,
                      minHeight: 8,
                      backgroundColor: appGreenSoft,
                      valueColor: AlwaysStoppedAnimation<Color>(color),
                    ),
                  ),
                  if (startLabel != null || endLabel != null) ...[
                    const SizedBox(height: 3),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            startLabel ?? '',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                        Text(
                          endLabel ?? '',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ],
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBioacousticOverview(AudioMetric? metric, int sampleCount) {
    return AppFieldHero(
      icon: Icons.graphic_eq,
      eyebrow: 'Paisaje sonoro',
      title: _bioacousticLevel(metric),
      subtitle: _bioacousticDescription(metric),
      status: AppStatusPill(text: '$sampleCount muestras', icon: Icons.waves),
      child: metric == null
          ? Text(
              'Cuando haya muestras, esta pantalla resumira el estado acustico antes de entrar en los indices tecnicos.',
              style: Theme.of(context).textTheme.bodySmall,
            )
          : Column(
              children: [
                _buildMetricLine(
                  icon: Icons.eco_outlined,
                  label: 'NDSI',
                  value: formatValue(metric.ndsi),
                  description:
                      'Balance entre biofonia y ruido. Valores positivos suelen indicar mayor peso biologico.',
                  progress: _rangeProgress(metric.ndsi, -1, 1),
                  startLabel: 'Ruido',
                  endLabel: 'Biofonia',
                ),
                _buildMetricLine(
                  icon: Icons.biotech_outlined,
                  label: 'BIO',
                  value: formatValue(metric.bio),
                  description:
                      'Energia acustica asociada a actividad biologica detectada en la muestra.',
                  progress: _boundedProgress(metric.bio),
                ),
                _buildMetricLine(
                  icon: Icons.show_chart,
                  label: 'ACI',
                  value: formatValue(metric.aci),
                  description:
                      'Complejidad acustica: sube cuando hay cambios y eventos sonoros en el audio.',
                  progress: _boundedProgress(metric.aci),
                ),
              ],
            ),
    );
  }

  Widget _buildBiodiversityPanel(Map<String, dynamic> data) {
    if (data.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay datos de biodiversidad disponibles.'),
      );
    }

    final abundance = _readNumber(data, 'abundancia');
    final richness = _readNumber(data, 'riqueza');
    final shannon = _readNumber(data, 'shannon');
    final simpson = _readNumber(data, 'simpson');
    final pielou = _readNumber(data, 'pielou');
    final quality = data['calidad']?.toString();

    return AppDataPanel(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (quality != null && quality.trim().isNotEmpty) ...[
            AppStatusPill(
              text: 'Calidad: $quality',
              icon: Icons.verified_outlined,
            ),
            const SizedBox(height: 8),
          ],
          _buildMetricLine(
            icon: Icons.eco,
            label: 'Abundancia',
            value: formatValue(abundance),
            description:
                'Cantidad de detecciones usadas para estimar actividad.',
            progress: _boundedProgress(abundance),
          ),
          _buildMetricLine(
            icon: Icons.grass,
            label: 'Riqueza de especies',
            value: formatValue(richness),
            description:
                'Numero de especies distintas detectadas en el periodo.',
            progress: _rangeProgress(richness, 0, 8),
          ),
          _buildMetricLine(
            icon: Icons.scatter_plot_outlined,
            label: 'Shannon',
            value: formatValue(shannon),
            description:
                'Combina riqueza y reparto de detecciones entre especies.',
            progress: _rangeProgress(shannon, 0, 3),
          ),
          _buildMetricLine(
            icon: Icons.pie_chart_outline,
            label: 'Simpson',
            value: formatValue(simpson),
            description: 'Ayuda a ver si pocas especies dominan el conjunto.',
            progress: _rangeProgress(simpson, 0, 1),
          ),
          _buildMetricLine(
            icon: Icons.balance_outlined,
            label: 'Equidad de Pielou',
            value: formatValue(pielou),
            description:
                'Mide si la actividad esta repartida de forma equilibrada.',
            progress: _rangeProgress(pielou, 0, 1),
          ),
        ],
      ),
    );
  }

  Widget _buildAcousticIndexPanel(AudioMetric? metric) {
    if (metric == null) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay metricas acusticas disponibles.'),
      );
    }

    return AppDataPanel(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const Icon(Icons.schedule_outlined),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Ultima muestra: ${formatTimestamp(metric.timestamp)}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          _buildMetricLine(
            icon: Icons.speed,
            label: 'RMS',
            value: formatValue(metric.rms),
            description:
                'Energia general del audio: sirve para detectar muestras muy silenciosas o saturadas.',
            progress: _boundedProgress(metric.rms),
          ),
          _buildMetricLine(
            icon: Icons.bar_chart,
            label: 'ADI',
            value: formatValue(metric.adi),
            description: 'Diversidad acustica por bandas de frecuencia.',
            progress: _rangeProgress(metric.adi, 0, 3),
          ),
          _buildMetricLine(
            icon: Icons.area_chart,
            label: 'AEI',
            value: formatValue(metric.aei),
            description:
                'Uniformidad acustica: ayuda a detectar dominancia en pocas bandas.',
            progress: _rangeProgress(metric.aei, 0, 1),
          ),
          _buildMetricLine(
            icon: Icons.multiline_chart,
            label: 'HT / HF',
            value: '${formatValue(metric.ht)} / ${formatValue(metric.hf)}',
            description:
                'Entropia temporal y frecuencial: describen distribucion del sonido en tiempo y frecuencia.',
            progress: _rangeProgress(metric.h ?? metric.ht, 0, 1),
          ),
        ],
      ),
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
              subtitle: Text(
                'ACI ${formatValue(recent[i].aci)} · BIO ${formatValue(recent[i].bio)}',
              ),
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
    final richness = _readNumber(biodiversity, 'riqueza');
    final shannon = _readNumber(biodiversity, 'shannon');

    if (ndsi != null && ndsi < -0.20) {
      notes.add(
        'NDSI bajo: el ruido domina sobre la actividad biologica reciente.',
      );
    } else if (ndsi != null && ndsi > 0.08) {
      notes.add(
        'NDSI positivo: hay senal biologica reconocible en la muestra.',
      );
    }

    if (richness != null && richness <= 3) {
      notes.add('Riqueza baja: se han detectado pocas especies en el periodo.');
    }

    if (shannon != null && shannon < 1) {
      notes.add('Shannon bajo: la diversidad relativa todavia es reducida.');
    }

    if (notes.isEmpty) {
      notes.add('Sin alertas claras con los datos disponibles.');
    }

    return AppDataPanel(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Lectura rapida',
            style: Theme.of(context).textTheme.titleMedium,
          ),
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
        _buildBioacousticOverview(latestMetric, metrics.length),
        const AppSectionTitle(
          title: 'Biodiversidad',
          subtitle: 'Resumen ecologico calculado sobre las detecciones.',
        ),
        _buildBiodiversityPanel(biodiversity),
        const AppSectionTitle(
          title: 'Interpretacion',
          subtitle: 'Traduccion breve de los indicadores principales.',
        ),
        _buildInterpretation(latestMetric, biodiversity),
        const AppSectionTitle(
          title: 'Indices acusticos',
          subtitle: 'Lectura tecnica de la ultima muestra de audio.',
        ),
        _buildAcousticIndexPanel(latestMetric),
        const AppSectionTitle(title: 'Muestras recientes'),
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
