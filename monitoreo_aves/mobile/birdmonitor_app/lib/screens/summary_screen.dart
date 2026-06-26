import 'package:flutter/material.dart';

import '../models/detection.dart';
import '../services/api_service.dart';

class SummaryScreen extends StatefulWidget {
  final String baseUrl;

  const SummaryScreen({
    super.key,
    required this.baseUrl,
  });

  @override
  State<SummaryScreen> createState() => _SummaryScreenState();
}

class _SummaryScreenState extends State<SummaryScreen> {
  late final ApiService api;

  late Future<List<Detection>> _detectionsFuture;
  late Future<Map<String, dynamic>> _streamFuture;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _loadData();
  }

  void _loadData() {
    _detectionsFuture = api.getDetections();
    _streamFuture = api.getStreamStatus();
  }

  Future<void> _refresh() async {
    setState(() {
      _loadData();
    });

    await Future.wait([
      _detectionsFuture,
      _streamFuture,
    ]);
  }

  String _formatConfidence(double confidence) {
    final value = confidence <= 1 ? confidence * 100 : confidence;
    return '${value.toStringAsFixed(1)}%';
  }

  String _formatStreamStatus(Map<String, dynamic> data) {
    final desired = data['stream_enabled'] ??
        data['desired_enabled'] ??
        data['desired_stream_enabled'];

    final running = data['actual_running'] ??
        data['stream_running'] ??
        data['real_running'] ??
        data['is_running'];

    return 'Deseado: ${desired ?? 'desconocido'} | Real: ${running ?? 'desconocido'}';
  }

  Widget _buildInfoCard({
    required IconData icon,
    required String title,
    required String value,
  }) {
    return Card(
      child: ListTile(
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text(
          value,
          style: const TextStyle(fontSize: 16),
        ),
      ),
    );
  }

  Widget _buildSummaryContent(
    List<Detection> detections,
    Map<String, dynamic> streamStatus,
  ) {
    final latest = detections.isNotEmpty ? detections.first : null;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Servidor',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        SelectableText(
          widget.baseUrl,
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 16),

        _buildInfoCard(
          icon: Icons.pets,
          title: 'Total de detecciones cargadas',
          value: detections.length.toString(),
        ),

        _buildInfoCard(
          icon: Icons.timeline,
          title: 'Última especie detectada',
          value: latest?.species ?? 'Sin detecciones',
        ),

        _buildInfoCard(
          icon: Icons.verified,
          title: 'Confianza última detección',
          value: latest == null ? 'Sin datos' : _formatConfidence(latest.confidence),
        ),

        _buildInfoCard(
          icon: Icons.access_time,
          title: 'Última actividad',
          value: latest?.timestamp ?? 'Sin datos',
        ),

        _buildInfoCard(
          icon: Icons.graphic_eq,
          title: 'Estado del streaming',
          value: _formatStreamStatus(streamStatus),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<List<dynamic>>(
        future: Future.wait([
          _detectionsFuture,
          _streamFuture,
        ]),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return ListView(
              children: [
                SizedBox(height: 240),
                Center(child: CircularProgressIndicator()),
              ],
            );
          }

          if (snapshot.hasError) {
            return ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text('Error cargando resumen: ${snapshot.error}'),
                  ),
                ),
              ],
            );
          }

          final detections = snapshot.data![0] as List<Detection>;
          final streamStatus = snapshot.data![1] as Map<String, dynamic>;

          return _buildSummaryContent(detections, streamStatus);
        },
      ),
    );
  }
}