import 'package:flutter/material.dart';

import '../models/devices.dart';
import '../services/api_service.dart';

class NodesScreen extends StatefulWidget {
  final String baseUrl;

  const NodesScreen({
    super.key,
    required this.baseUrl,
  });

  @override
  State<NodesScreen> createState() => _NodesScreenState();
}

class _NodesScreenState extends State<NodesScreen> {
  late final ApiService api;
  late Future<List<Device>> _devicesFuture;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _devicesFuture = api.getDevices();
  }

  Future<void> _refresh() async {
    setState(() {
      _devicesFuture = api.getDevices();
    });

    await _devicesFuture;
  }

  String _coordinates(Device device) {
    if (device.lat == null || device.lon == null) {
      return 'Coordenadas no disponibles';
    }

    return '${device.lat!.toStringAsFixed(6)}, ${device.lon!.toStringAsFixed(6)}';
  }

  Widget _buildDeviceCard(Device device) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.memory),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    device.name,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text('ID: ${device.id}'),
            const SizedBox(height: 4),
            Text('Ubicación: ${device.location ?? 'No especificada'}'),
            const SizedBox(height: 4),
            Text('Coordenadas: ${_coordinates(device)}'),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<List<Device>>(
        future: _devicesFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return ListView(
              children: const [
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
                    child: Text('Error cargando nodos: ${snapshot.error}'),
                  ),
                ),
              ],
            );
          }

          final devices = snapshot.data ?? [];

          if (devices.isEmpty) {
            return ListView(
              padding: const EdgeInsets.all(16),
              children: const [
                Card(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: Text('No hay nodos registrados'),
                  ),
                ),
              ],
            );
          }

          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: devices.length,
            itemBuilder: (context, index) {
              return _buildDeviceCard(devices[index]);
            },
          );
        },
      ),
    );
  }
}