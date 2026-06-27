import 'package:flutter/material.dart';

import '../models/devices.dart';
import '../services/api_service.dart';
import '../widgets/app_ui.dart';

class NodesScreen extends StatefulWidget {
  final String baseUrl;

  const NodesScreen({super.key, required this.baseUrl});

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
    return AppDataPanel(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: appGreenSoft,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Padding(
                  padding: EdgeInsets.all(10),
                  child: Icon(Icons.memory),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  device.name,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              AppStatusPill(text: '#${device.id}', icon: Icons.tag),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            device.location ?? 'Ubicacion no especificada',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 6),
          Text(
            _coordinates(device),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  Widget _buildNodesGrid(List<Device> devices) {
    if (devices.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay estaciones registradas.'),
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
            for (final device in devices)
              SizedBox(width: width, child: _buildDeviceCard(device)),
          ],
        );
      },
    );
  }

  Widget _buildContent(List<Device> devices) {
    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.place,
          title: 'Estaciones',
          subtitle: 'Puntos de monitorizacion conectados al sistema.',
          trailing: AppStatusPill(
            text: devices.length.toString(),
            icon: Icons.place,
          ),
        ),
        const AppSectionTitle(title: 'Estaciones registradas'),
        _buildNodesGrid(devices),
      ],
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
                  child: Text('Error cargando estaciones: ${snapshot.error}'),
                ),
              ],
            );
          }

          return _buildContent(snapshot.data ?? []);
        },
      ),
    );
  }
}