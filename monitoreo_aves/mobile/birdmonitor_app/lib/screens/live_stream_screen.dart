import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../services/api_service.dart';
import '../widgets/app_ui.dart';

class LiveStreamScreen extends StatefulWidget {
  final String baseUrl;

  const LiveStreamScreen({super.key, required this.baseUrl});

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
  String? playerNotice;
  String? playerDetails;

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
      if (mounted) {
        setState(() {
          changingStream = false;
        });
      }
    }
  }

  Future<void> _connectPlayer() async {
    setState(() {
      loadingPlayer = true;
      error = null;
      playerNotice = null;
      playerDetails = null;
    });

    if (kIsWeb) {
      setState(() {
        loadingPlayer = false;
        playerNotice =
            'Edge no reproduce HLS (.m3u8) de forma nativa dentro de Flutter Web. '
            'La escucha queda activada en el nodo; valida el reproductor en Android/iOS '
            'o usa la URL HLS con un reproductor compatible.';
      });
      return;
    }

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
        playerNotice =
            'No se pudo cargar el reproductor HLS en este dispositivo.';
        playerDetails = e.toString();
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

  bool? _readBool(List<String> keys) {
    final data = streamStatus ?? {};

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

  String _statusLabel(bool? value) {
    if (value == true) return 'Activado';
    if (value == false) return 'Detenido';
    return 'Desconocido';
  }

  bool get _showPlayerSection {
    final controller = _controller;
    return !kIsWeb ||
        loadingPlayer ||
        (controller != null && controller.value.isInitialized);
  }

  Widget _buildEndpointCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.graphic_eq,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Stream HLS',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                IconButton(
                  tooltip: 'Actualizar estado',
                  onPressed: _loadStatus,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text('URL HLS', style: Theme.of(context).textTheme.bodySmall),
            SelectableText(
              hlsUrl,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (pageUrl != null) ...[
              const SizedBox(height: 10),
              Text(
                'Pagina del stream',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              SelectableText(
                pageUrl!,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
          ],
        ),
      ),
    );
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

    final desired = _readBool([
      'stream_enabled',
      'desired_enabled',
      'desired_stream_enabled',
    ]);

    final real = _readBool([
      'actual_running',
      'stream_running',
      'real_running',
      'is_running',
    ]);

    final detail = _readValue(['detail', 'status_detail', 'message']);
    final subtitle = desired == true && real == false
        ? 'Solicitado: activado | Nodo: esperando confirmacion'
        : 'Solicitado: ${_statusLabel(desired)} | Nodo: ${_statusLabel(real)}';

    return Card(
      child: ListTile(
        leading: const Icon(Icons.sensors),
        title: const Text('Estado del stream'),
        subtitle: Text(
          detail == 'desconocido' ? subtitle : '$subtitle\n$detail',
        ),
      ),
    );
  }

  Widget _buildControls(BoxConstraints constraints) {
    final disabled = changingStream || loadingStatus;
    final wide = constraints.maxWidth >= 720;

    final actions = [
      ElevatedButton.icon(
        onPressed: disabled ? null : () => _setStream(true),
        icon: const Icon(Icons.play_arrow),
        label: const Text('Activar'),
      ),
      OutlinedButton.icon(
        onPressed: disabled ? null : _connectPlayer,
        icon: const Icon(Icons.speaker),
        label: const Text('Reproductor'),
      ),
      OutlinedButton.icon(
        onPressed: disabled ? null : () => _setStream(false),
        icon: const Icon(Icons.stop),
        label: const Text('Detener'),
      ),
    ];

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Control de escucha',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            if (wide)
              Row(
                children: [
                  for (var i = 0; i < actions.length; i++) ...[
                    if (i > 0) const SizedBox(width: 10),
                    Expanded(child: actions[i]),
                  ],
                ],
              )
            else
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (var i = 0; i < actions.length; i++) ...[
                    if (i > 0) const SizedBox(height: 8),
                    actions[i],
                  ],
                ],
              ),
            if (changingStream) ...[
              const SizedBox(height: 16),
              const Center(child: CircularProgressIndicator()),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildError() {
    final currentError = error;

    if (currentError == null) {
      return const SizedBox.shrink();
    }

    return Card(
      child: ListTile(
        leading: Icon(
          Icons.error_outline,
          color: Theme.of(context).colorScheme.error,
        ),
        title: const Text('No se pudo consultar el stream'),
        subtitle: Text(
          currentError,
          style: TextStyle(color: Theme.of(context).colorScheme.error),
        ),
      ),
    );
  }

  Widget _buildPlayerNotice() {
    final notice = playerNotice;

    if (notice == null) {
      return const SizedBox.shrink();
    }

    return Card(
      child: ExpansionTile(
        leading: Icon(
          Icons.info_outline,
          color: Theme.of(context).colorScheme.secondary,
        ),
        title: const Text('Reproductor no disponible en esta vista'),
        subtitle: Text(notice),
        children: [
          if (playerDetails != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: SelectableText(
                playerDetails!,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
        ],
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
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              Icon(
                Icons.speaker_outlined,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  kIsWeb
                      ? 'En Edge se muestra el control del stream; el audio HLS se valida mejor en movil.'
                      : 'Reproductor no conectado',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ),
      );
    }

    return Card(
      clipBehavior: Clip.antiAlias,
      child: AspectRatio(
        aspectRatio: controller.value.aspectRatio,
        child: VideoPlayer(controller),
      ),
    );
  }

  Widget _buildContent(BoxConstraints constraints) {
    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.headphones,
          title: 'Escucha en directo',
          subtitle:
              'Controla el stream del nodo y consulta las URLs de salida HLS.',
          trailing: IconButton(
            tooltip: 'Actualizar estado',
            onPressed: _loadStatus,
            icon: const Icon(Icons.refresh),
          ),
        ),
        _buildStatusCard(),
        _buildControls(constraints),
        _buildEndpointCard(),
        _buildError(),
        _buildPlayerNotice(),
        if (_showPlayerSection) ...[
          const AppSectionTitle(title: 'Reproductor'),
          _buildPlayer(),
        ],
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return _buildContent(constraints);
      },
    );
  }
}