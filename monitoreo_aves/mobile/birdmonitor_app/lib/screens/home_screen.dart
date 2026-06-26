import 'package:flutter/material.dart';

import '../models/detection.dart';
import '../services/api_service.dart';
import 'connection_screen.dart';
import 'live_screen.dart';

class HomeScreen extends StatefulWidget {
  final String baseUrl;

  const HomeScreen({
    super.key,
    required this.baseUrl,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
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

  Future<void> _changeServer() async {
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (_) => const ConnectionScreen(),
      ),
    );
  }

  String _formatConfidence(double confidence) {
    final value = confidence <= 1 ? confidence * 100 : confidence;
    return '${value.toStringAsFixed(1)}%';
  }

  String _streamText(Map<String, dynamic> data) {
    final desired = data['stream_enabled'] ??
        data['desired_enabled'] ??
        data['desired_stream_enabled'];

    final running = data['actual_running'] ??
        data['stream_running'] ??
        data['real_running'] ??
        data['is_running'];

    return 'Deseado: ${desired ?? 'desconocido'} | Real: ${running ?? 'desconocido'}';
  }

  Widget _buildStreamCard() {
    return FutureBuilder<Map<String, dynamic>>(
      future: _streamFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Card(
            child: ListTile(
              leading: CircularProgressIndicator(),
              title: Text('Estado del streaming'),
              subtitle: Text('Consultando estado...'),
            ),
          );
        }

        if (snapshot.hasError) {
          return Card(
            child: ListTile(
              leading: const Icon(Icons.error_outline),
              title: const Text('Estado del streaming'),
              subtitle: Text(snapshot.error.toString()),
            ),
          );
        }

        final data = snapshot.data ?? {};

        return Card(
          child: ListTile(
            leading: const Icon(Icons.graphic_eq),
            title: const Text('Estado del streaming'),
            subtitle: Text(_streamText(data)),
          ),
        );
      },
    );
  }

  Widget _buildDetectionsList() {
    return FutureBuilder<List<Detection>>(
      future: _detectionsFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Padding(
            padding: EdgeInsets.all(24),
            child: Center(child: CircularProgressIndicator()),
          );
        }

        if (snapshot.hasError) {
          return Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Text('Error cargando detecciones: ${snapshot.error}'),
            ),
          );
        }

        final detections = snapshot.data ?? [];

        if (detections.isEmpty) {
          return const Card(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Text('Todavía no hay detecciones registradas'),
            ),
          );
        }

        return Column(
          children: detections.take(10).map((detection) {
            return Card(
              child: ListTile(
                leading: const Icon(Icons.pets),
                title: Text(detection.species),
                subtitle: Text(detection.timestamp),
                trailing: Text(
                  _formatConfidence(detection.confidence),
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
              ),
            );
          }).toList(),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('BirdMonitor'),
        actions: [
          IconButton(
            onPressed: _refresh,
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            onPressed: _changeServer,
            icon: const Icon(Icons.settings),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Servidor',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(
              widget.baseUrl,
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            _buildStreamCard(),
            const SizedBox(height: 12),
            ElevatedButton.icon(
            onPressed: () {
                Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (_) => LiveStreamScreen(baseUrl: widget.baseUrl),
                ),
                );
            },
            icon: const Icon(Icons.headphones),
            label: const Text('Abrir escucha en directo'),
            ),
            const SizedBox(height: 24),
            Text(
              'Últimas detecciones',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            _buildDetectionsList(),
          ],
        ),
      ),
    );
  }
}