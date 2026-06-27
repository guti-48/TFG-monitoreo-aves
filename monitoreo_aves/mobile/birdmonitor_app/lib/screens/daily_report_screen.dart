import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_ui.dart';

class DailyReportScreen extends StatefulWidget {
  final String baseUrl;

  const DailyReportScreen({super.key, required this.baseUrl});

  @override
  State<DailyReportScreen> createState() => _DailyReportScreenState();
}

class _DailyReportScreenState extends State<DailyReportScreen> {
  late final ApiService api;

  DateTime selectedDate = DateTime.now();
  late Future<dynamic> _dailyReportFuture;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _loadData();
  }

  String get _formattedDate => formatApiDate(selectedDate);

  void _loadData() {
    _dailyReportFuture = api.getDailyActivity(_formattedDate);
  }

  Future<void> _refresh() async {
    setState(() {
      _loadData();
    });

    await _dailyReportFuture;
  }

  Future<void> _selectDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: selectedDate,
      firstDate: DateTime(2020),
      lastDate: DateTime.now().add(const Duration(days: 1)),
    );

    if (picked == null) return;

    setState(() {
      selectedDate = picked;
      _loadData();
    });
  }

  String formatValue(dynamic value) {
    if (value == null) return 'Sin datos';

    if (value is List) {
      if (value.isEmpty) return 'Sin especies';
      return value.join(', ');
    }

    if (value is Map) {
      if (value.isEmpty) return 'Sin datos';

      return value.entries
          .map((entry) => '${entry.key}: ${entry.value}')
          .join(' | ');
    }

    if (value is int) return value.toString();

    if (value is double) {
      if (value == value.roundToDouble()) return value.toInt().toString();
      if (value.abs() < 1) return value.toStringAsFixed(4);
      return value.toStringAsFixed(2);
    }

    if (value is String) {
      final parsed = double.tryParse(value);

      if (parsed != null) return formatValue(parsed);

      return value;
    }

    return value.toString();
  }

  String prettyLabel(String key) {
    switch (key) {
      case 'hour':
      case 'hora':
      case 'h':
        return 'Hora';
      case 'total_detecciones':
      case 'detections':
      case 'num_detections':
      case 'count':
      case 'total':
        return 'Total de detecciones';
      case 'confianza_media':
      case 'avg_confidence':
      case 'confidence_avg':
        return 'Confianza media';
      case 'especies_activas':
      case 'active_species':
      case 'species_count':
        return 'Especies activas';
      case 'lista_especies':
      case 'species':
      case 'especies':
        return 'Lista de especies';
      case 'activity':
      case 'actividad':
        return 'Actividad';
      case 'date':
      case 'fecha':
        return 'Fecha';
      default:
        return key
            .replaceAll('_', ' ')
            .replaceFirstMapped(
              RegExp(r'^[a-z]'),
              (match) => match.group(0)!.toUpperCase(),
            );
    }
  }

  num _toNumber(dynamic value) {
    if (value is int) return value;
    if (value is double) return value;
    if (value is String) return num.tryParse(value) ?? 0;
    return 0;
  }

  bool _hourHasActivity(dynamic item) {
    if (item is! Map<String, dynamic>) return true;

    final total = _toNumber(
      item['total_detecciones'] ??
          item['detections'] ??
          item['num_detections'] ??
          item['count'] ??
          item['total'],
    );

    final activeSpecies = _toNumber(
      item['especies_activas'] ??
          item['active_species'] ??
          item['species_count'],
    );

    final speciesList =
        item['lista_especies'] ?? item['species'] ?? item['especies'];
    final hasSpeciesList = speciesList is List && speciesList.isNotEmpty;

    return total > 0 || activeSpecies > 0 || hasSpeciesList;
  }

  List<dynamic> _extractHourlyData(dynamic data) {
    if (data is List) return data;

    if (data is Map<String, dynamic>) {
      final possibleKeys = [
        'hourly_activity',
        'activity_by_hour',
        'detections_by_hour',
        'hours',
        'data',
        'results',
      ];

      for (final key in possibleKeys) {
        final value = data[key];

        if (value is List) return value;
      }
    }

    return [];
  }

  Map<String, dynamic> _extractSummaryData(dynamic data) {
    if (data is Map<String, dynamic>) {
      final summary = <String, dynamic>{};

      data.forEach((key, value) {
        if (value is! List && value is! Map) {
          summary[key] = value;
        }
      });

      return summary;
    }

    return {};
  }

  Widget _buildDateSelector() {
    return AppDataPanel(
      child: ListTile(
        leading: const Icon(Icons.calendar_month),
        title: const Text('Fecha del informe'),
        subtitle: Text(formatDateOnly(selectedDate)),
        trailing: FilledButton.tonal(
          onPressed: _selectDate,
          child: const Text('Cambiar'),
        ),
      ),
    );
  }

  Widget _buildSummaryCard(Map<String, dynamic> summary) {
    if (summary.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay resumen general para esta fecha.'),
      );
    }

    return AppMetricGrid(
      children: summary.entries.map((entry) {
        return AppMetricCard(
          icon: Icons.today,
          label: prettyLabel(entry.key),
          value: formatValue(entry.value),
        );
      }).toList(),
    );
  }

  Widget _buildHourCard(dynamic item) {
    if (item is Map<String, dynamic>) {
      final hour = item['hour'] ?? item['hora'] ?? item['h'] ?? '-';

      final entries = item.entries.where((entry) {
        return entry.key != 'hour' && entry.key != 'hora' && entry.key != 'h';
      }).toList();

      return AppDataPanel(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.schedule),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    formatHour(hour),
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            if (entries.isEmpty)
              const Text('Sin datos adicionales')
            else
              ...entries.map((entry) {
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          prettyLabel(entry.key),
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          formatValue(entry.value),
                          textAlign: TextAlign.end,
                          style: const TextStyle(fontWeight: FontWeight.bold),
                        ),
                      ),
                    ],
                  ),
                );
              }),
          ],
        ),
      );
    }

    return AppDataPanel(
      padding: const EdgeInsets.all(16),
      child: Text(formatValue(item)),
    );
  }

  Widget _buildHourlyActivity(List<dynamic> hourlyData) {
    if (hourlyData.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay actividad horaria para esta fecha.'),
      );
    }

    final activeHours = hourlyData.where(_hourHasActivity).toList();

    if (activeHours.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text(
          'No se registro actividad acustica relevante en esta fecha.',
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.maxWidth >= 760 ? 2 : 1;
        final gap = 10.0;
        final width = (constraints.maxWidth - (columns - 1) * gap) / columns;

        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: [
            for (final hour in activeHours)
              SizedBox(width: width, child: _buildHourCard(hour)),
          ],
        );
      },
    );
  }

  Widget _buildContent(dynamic data) {
    final summary = _extractSummaryData(data);
    final hourlyData = _extractHourlyData(data);

    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.today,
          title: 'Informe diario',
          subtitle: 'Actividad acustica resumida por fecha y franja horaria.',
          trailing: AppStatusPill(
            text: formatDateOnly(selectedDate),
            icon: Icons.calendar_month,
          ),
        ),
        _buildDateSelector(),
        const AppSectionTitle(
          title: 'Resumen diario',
          subtitle: 'Valores agregados para la fecha seleccionada.',
        ),
        _buildSummaryCard(summary),
        const AppSectionTitle(
          title: 'Actividad por hora',
          subtitle: 'Solo se muestran las horas con actividad registrada.',
        ),
        _buildHourlyActivity(hourlyData),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<dynamic>(
        future: _dailyReportFuture,
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
                _buildDateSelector(),
                AppDataPanel(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    'Error cargando informe diario: ${snapshot.error}',
                  ),
                ),
              ],
            );
          }

          return _buildContent(snapshot.data);
        },
      ),
    );
  }
}