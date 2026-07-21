import 'package:flutter/material.dart';

import '../models/detection.dart';
import '../models/devices.dart';
import '../services/api_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_ui.dart';
import 'live_stream_screen.dart';

class NodesScreen extends StatefulWidget {
  final String baseUrl;

  const NodesScreen({super.key, required this.baseUrl});

  @override
  State<NodesScreen> createState() => _NodesScreenState();
}

class _NodesScreenState extends State<NodesScreen> {
  late final ApiService api;
  late Future<List<Device>> _devicesFuture;
  late Future<List<Detection>> _detectionsFuture;
  late Future<Map<String, dynamic>> _streamFuture;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _loadData();
  }

  void _loadData() {
    _devicesFuture = _safeDevices();
    _detectionsFuture = _safeDetections();
    _streamFuture = _safeStream();
  }

  Future<List<Device>> _safeDevices() async {
    try {
      return await api.getDevices();
    } catch (_) {
      return [];
    }
  }

  Future<List<Detection>> _safeDetections() async {
    try {
      return await api.getDetections();
    } catch (_) {
      return [];
    }
  }

  Future<Map<String, dynamic>> _safeStream() async {
    try {
      return await api.getStreamStatus();
    } catch (e) {
      return {'error': e.toString()};
    }
  }

  Future<void> _refresh() async {
    setState(() {
      _loadData();
    });

    await Future.wait([_devicesFuture, _detectionsFuture, _streamFuture]);
  }

  String _coordinates(Device device) {
    if (device.lat == null || device.lon == null) {
      return 'Coordenadas no disponibles';
    }

    return '${device.lat!.toStringAsFixed(6)}, ${device.lon!.toStringAsFixed(6)}';
  }

  bool? _readBool(Map<String, dynamic> data, List<String> keys) {
    for (final key in keys) {
      final value = data[key];
      if (value is bool) return value;
      if (value is String) {
        final normalized = value.toLowerCase();
        if (normalized == 'true') return true;
        if (normalized == 'false') return false;
      }
    }

    return null;
  }

  String _streamLabel(bool? running, bool hasError) {
    if (hasError) return 'Sin confirmar';
    if (running == true) return 'Online';
    if (running == false) return 'Offline';
    return 'Registrada';
  }

  Color _streamColor(bool? running, bool hasError) {
    if (hasError) return Theme.of(context).colorScheme.error;
    if (running == true) return Theme.of(context).colorScheme.primary;
    if (running == false) return Theme.of(context).colorScheme.secondary;
    return Theme.of(context).colorScheme.secondary;
  }

  Detection? _latestForDevice(Device device, List<Detection> detections) {
    for (final detection in detections) {
      if (detection.deviceId == device.id) return detection;
    }

    return detections.isNotEmpty ? detections.first : null;
  }

  void _openStream(Device device) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => LiveStreamScreen(
          baseUrl: widget.baseUrl,
          nodeName: device.name,
        ),
      ),
    );
  }

  Widget _buildDeviceCard(
    Device device,
    Detection? latest,
    bool? running,
    bool hasError,
  ) {
    final statusLabel = _streamLabel(running, hasError);
    final statusColor = _streamColor(running, hasError);

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
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      device.name,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      device.location ?? 'Ubicacion no especificada',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              AppStatusPill(
                text: statusLabel,
                icon: running == true
                    ? Icons.radio_button_checked
                    : Icons.radio_button_unchecked,
                color: statusColor,
              ),
            ],
          ),
          const SizedBox(height: 14),
          AppSoundBars(active: running == true, height: 34, color: statusColor),
          const SizedBox(height: 12),
          AppDetailRow(
            icon: Icons.place_outlined,
            label: 'Coordenadas',
            value: _coordinates(device),
          ),
          const SizedBox(height: 6),
          AppDetailRow(
            icon: Icons.eco_outlined,
            label: 'Ultima especie',
            value: latest?.displaySpecies ?? 'Sin actividad reciente',
          ),
          const SizedBox(height: 6),
          AppDetailRow(
            icon: Icons.schedule,
            label: 'Ultima sincronizacion',
            value: latest == null
                ? 'Sin datos'
                : formatTimestamp(latest.timestamp),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => _openStream(device),
            icon: const Icon(Icons.headphones),
            label: const Text('Abrir escucha'),
          ),
        ],
      ),
    );
  }

  Widget _buildMapPanel(List<Device> devices, bool? running, bool hasError) {
    final mainDevice = devices.isNotEmpty ? devices.first : null;

    return AppFieldHero(
      icon: Icons.map_outlined,
      eyebrow: 'Mis estaciones',
      title: mainDevice?.location ?? 'Mapa privado de estaciones',
      subtitle: mainDevice == null
          ? 'Aun no hay estaciones registradas.'
          : _coordinates(mainDevice),
      status: AppStatusPill(
        text: _streamLabel(running, hasError),
        icon: running == true ? Icons.sensors : Icons.sensors_off_outlined,
        color: _streamColor(running, hasError),
      ),
      child: Container(
        height: 150,
        decoration: BoxDecoration(
          color: appPanelMuted,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: appPanelBorder),
        ),
        child: Stack(
          children: [
            Positioned.fill(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    border: Border.all(color: appGreenSoft, width: 2),
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
              ),
            ),
            Center(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: const Padding(
                  padding: EdgeInsets.all(14),
                  child: Icon(Icons.location_on, color: Colors.white),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNodesGrid(
    List<Device> devices,
    List<Detection> detections,
    bool? running,
    bool hasError,
  ) {
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
              SizedBox(
                width: width,
                child: _buildDeviceCard(
                  device,
                  _latestForDevice(device, detections),
                  running,
                  hasError,
                ),
              ),
          ],
        );
      },
    );
  }

  Widget _buildContent(
    List<Device> devices,
    List<Detection> detections,
    Map<String, dynamic> stream,
  ) {
    final running = _readBool(stream, [
      'actual_running',
      'stream_running',
      'real_running',
      'is_running',
    ]);
    final hasError = stream['error'] != null;

    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.place,
          title: 'Estaciones',
          subtitle: 'Mapa privado de tus puntos de escucha.',
          trailing: AppStatusPill(
            text: devices.length.toString(),
            icon: Icons.place,
          ),
        ),
        _buildMapPanel(devices, running, hasError),
        const AppSectionTitle(
          title: 'Estaciones registradas',
          subtitle: 'Estado, ultima especie y acceso directo a escucha.',
        ),
        _buildNodesGrid(devices, detections, running, hasError),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<List<dynamic>>(
        future: Future.wait([_devicesFuture, _detectionsFuture, _streamFuture]),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const AppPage(
              children: [
                SizedBox(height: 220),
                Center(child: CircularProgressIndicator()),
              ],
            );
          }

          final data = snapshot.data;

          if (snapshot.hasError || data == null) {
            return AppPage(
              children: [
                AppDataPanel(
                  padding: const EdgeInsets.all(16),
                  child: Text('Error cargando estaciones: ${snapshot.error}'),
                ),
              ],
            );
          }

          return _buildContent(
            data[0] as List<Device>,
            data[1] as List<Detection>,
            data[2] as Map<String, dynamic>,
          );
        },
      ),
    );
  }
}