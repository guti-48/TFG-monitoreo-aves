import 'package:flutter/material.dart';

import '../models/detection.dart';
import '../services/api_service.dart';

class DetectionsScreen extends StatefulWidget {
  final String baseUrl;

  const DetectionsScreen({
    super.key,
    required this.baseUrl,
  });

  @override
  State<DetectionsScreen> createState() => _DetectionsScreenState();
}

class _DetectionsScreenState extends State<DetectionsScreen> {
  late final ApiService api;
  late Future<List<Detection>> _detectionsFuture;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _detectionsFuture = api.getDetections();
  }

  Future<void> _refresh() async {
    setState(() {
      _detectionsFuture = api.getDetections();
    });

    await _detectionsFuture;
  }

  String _formatConfidence(double confidence) {
    final value = confidence <= 1 ? confidence * 100 : confidence;
    return '${value.toStringAsFixed(1)}%';
  }

  Widget _buildDetectionCard(Detection detection) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.pets),
        title: Text(detection.species),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(detection.timestamp),
            if (detection.filename != null && detection.filename!.isNotEmpty)
              Text(
                detection.filename!,
                style: Theme.of(context).textTheme.bodySmall,
              ),
          ],
        ),
        trailing: Text(
          _formatConfidence(detection.confidence),
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<List<Detection>>(
        future: _detectionsFuture,
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
                    padding: EdgeInsets.all(16),
                    child: Text('Error cargando detecciones'),
                  ),
                ),
              ],
            );
          }

          final detections = snapshot.data ?? [];

          if (detections.isEmpty) {
            return ListView(
              padding: EdgeInsets.all(16),
              children: [
                Card(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Text('Todavía no hay detecciones registradas'),
                  ),
                ),
              ],
            );
          }

          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: detections.length,
            itemBuilder: (context, index) {
              return _buildDetectionCard(detections[index]);
            },
          );
        },
      ),
    );
  }
}