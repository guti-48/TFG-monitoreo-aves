import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../services/api_service.dart';

class LiveStreamScreen extends StatefulWidget {
  final String baseUrl;

  const LiveStreamScreen({
    super.key,
    required this.baseUrl,
  });

  @override
  State<LiveStreamScreen> createState() => _LiveStreamScreenState();
}

class _LiveStreamScreenState extends State<LiveStreamScreen> {
  late final ApiService api;
  late String hlsUrl;
    String? pageUrl;

  Map<String, dynamic>? streamStatus;
  VideoPlayerController? _controller;

  bool loadingStatus = true;
  bool changingStream = false;
  bool loadingPlayer = false;
  String? error;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    hlsUrl = api.getHlsUrl();
    _loadStatus();
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _loadStatus() async {
    setState(() {
      loadingStatus = true;
      error = null;
    });

    try {
      final status = await api.getStreamStatus();

        final backendHlsUrl = status['hls_url']?.toString();
        final backendPageUrl = status['page_url']?.toString();

        if (!mounted) return;

        setState(() {
        streamStatus = status;

        if (backendHlsUrl != null && backendHlsUrl.isNotEmpty) {
            hlsUrl = backendHlsUrl;
        }

        if (backendPageUrl != null && backendPageUrl.isNotEmpty) {
            pageUrl = backendPageUrl;
        }

        loadingStatus = false;
    });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        error = e.toString();
        loadingStatus = false;
      });
    }
  }

  Future<void> _setStream(bool enabled) async {
    setState(() {
      changingStream = true;
      error = null;
    });

    try {
      await api.setStreamEnabled(enabled);
      await _loadStatus();
    } catch (e) {
      if (!mounted) return;

      setState(() {
        error = e.toString();
      });
    } finally {
      if (!mounted) return;

      setState(() {
        changingStream = false;
      });
    }
  }

  Future<void> _connectPlayer() async {
    setState(() {
      loadingPlayer = true;
      error = null;
    });

    try {
      await _controller?.dispose();

      final controller = VideoPlayerController.networkUrl(Uri.parse(hlsUrl));
      await controller.initialize();
      await controller.play();

      if (!mounted) return;

      setState(() {
        _controller = controller;
        loadingPlayer = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        loadingPlayer = false;
        error =
        'No se pudo cargar el reproductor HLS. '
        'Si estás probando en Edge/Flutter Web, puede ser una limitación del navegador. '
        'La reproducción HLS se validará mejor en Android/iOS. Detalle: $e';
      });
    }
  }

  String _readValue(List<String> keys) {
    final data = streamStatus ?? {};

    for (final key in keys) {
      if (data.containsKey(key)) {
        return data[key].toString();
      }
    }

    return 'desconocido';
  }

  Widget _buildStatusCard() {
    if (loadingStatus) {
      return const Card(
        child: ListTile(
          leading: CircularProgressIndicator(),
          title: Text('Estado del stream'),
          subtitle: Text('Consultando...'),
        ),
      );
    }

    final desired = _readValue([
      'stream_enabled',
      'desired_enabled',
      'desired_stream_enabled',
    ]);

    final real = _readValue([
        'actual_running',
        'stream_running',
        'real_running',
        'is_running',
    ]);

    return Card(
      child: ListTile(
        leading: const Icon(Icons.graphic_eq),
        title: const Text('Estado del stream'),
        subtitle: Text('Deseado: $desired | Real: $real'),
      ),
    );
  }

  Widget _buildPlayer() {
    final controller = _controller;

    if (loadingPlayer) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Center(child: CircularProgressIndicator()),
        ),
      );
    }

    if (controller == null || !controller.value.isInitialized) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text('Reproductor no conectado'),
        ),
      );
    }

    return Card(
      child: AspectRatio(
        aspectRatio: controller.value.aspectRatio,
        child: VideoPlayer(controller),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final disabled = changingStream || loadingStatus;

    return ListView(
    padding: const EdgeInsets.all(16),
    children: [
      Row(
        children: [
          Expanded(
            child: Text(
              'Stream HLS',
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
          IconButton(
            onPressed: _loadStatus,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      const SizedBox(height: 8),
      SelectableText(
        hlsUrl,
        style: Theme.of(context).textTheme.bodySmall,
      ),
      const SizedBox(height: 16),

      _buildStatusCard(),

      const SizedBox(height: 16),

      ElevatedButton.icon(
        onPressed: disabled ? null : () => _setStream(true),
        icon: const Icon(Icons.play_arrow),
        label: const Text('Activar escucha'),
      ),

      const SizedBox(height: 8),

      ElevatedButton.icon(
        onPressed: disabled ? null : _connectPlayer,
        icon: const Icon(Icons.speaker),
        label: const Text('Conectar reproductor'),
      ),

      const SizedBox(height: 8),

      ElevatedButton.icon(
        onPressed: disabled ? null : () => _setStream(false),
        icon: const Icon(Icons.stop),
        label: const Text('Detener escucha'),
      ),

      if (changingStream) ...[
        const SizedBox(height: 16),
        const Center(child: CircularProgressIndicator()),
      ],

      if (error != null) ...[
        const SizedBox(height: 16),
        Text(
          error!,
          style: const TextStyle(color: Colors.red),
        ),
      ],

      const SizedBox(height: 24),

      Text(
        'Reproductor',
        style: Theme.of(context).textTheme.titleLarge,
      ),
      const SizedBox(height: 8),
      _buildPlayer(),
    ],
  );
  }
}