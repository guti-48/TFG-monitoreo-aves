import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../services/api_service.dart';
import '../widgets/app_ui.dart';

class LiveStreamScreen extends StatefulWidget {
  final String baseUrl;
  final String nodeName;

  const LiveStreamScreen({
    super.key,
    required this.baseUrl,
    this.nodeName = 'birdmonitor',
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
  String? playerNotice;
  String? playerDetails;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    hlsUrl = api.getHlsUrl(streamPath: _streamPathForNode(widget.nodeName));
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
      final status = await api.getStreamStatus(nodeName: widget.nodeName);

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
      await api.setStreamEnabled(
        enabled,
        nodeName: widget.nodeName,
        streamPath: _streamPathForNode(widget.nodeName),
      );
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

  String _streamPathForNode(String nodeName) {
    final cleanName = nodeName
        .trim()
        .replaceAll(RegExp(r'[^A-Za-z0-9_.-]+'), '-')
        .replaceAll(RegExp(r'^-+|-+$'), '');

    return '${cleanName.isEmpty ? 'birdmonitor' : cleanName}-audio';
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

  String _listeningState(bool? desired, bool? real) {
    if (real == true) return 'Escuchando';
    if (desired == true && real != true) return 'Esperando nodo';
    if (desired == false || real == false) return 'Stream detenido';
    return 'Estado sin confirmar';
  }

  Color _stateColor(bool? desired, bool? real) {
    if (real == true) return Theme.of(context).colorScheme.primary;
    if (desired == true && real != true) {
      return Theme.of(context).colorScheme.secondary;
    }
    if (desired == false || real == false) {
      return Theme.of(context).colorScheme.error;
    }
    return Theme.of(context).colorScheme.secondary;
  }

  bool get _showPlayerSection {
    final controller = _controller;
    return !kIsWeb ||
        loadingPlayer ||
        (controller != null && controller.value.isInitialized);
  }

  Widget _buildEndpointCard() {
    return AppDataPanel(
      padding: EdgeInsets.zero,
      child: ExpansionTile(
        leading: const Icon(Icons.settings_input_antenna),
        title: const Text('Avanzado'),
        subtitle: const Text('URL HLS y pagina tecnica del stream'),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'URL HLS',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
          const SizedBox(height: 4),
          Align(
            alignment: Alignment.centerLeft,
            child: SelectableText(
              hlsUrl,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
          if (pageUrl != null) ...[
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Pagina del stream',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            const SizedBox(height: 4),
            Align(
              alignment: Alignment.centerLeft,
              child: SelectableText(
                pageUrl!,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildListeningHero() {
    if (loadingStatus) {
      return const AppDataPanel(
        padding: EdgeInsets.all(24),
        child: Center(
          child: Column(
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 12),
              Text('Consultando estado del nodo...'),
            ],
          ),
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
    final state = _listeningState(desired, real);
    final subtitle = detail == 'desconocido'
        ? 'Escucha: ${_statusLabel(desired)} - Nodo: ${_statusLabel(real)}'
        : detail;

    return AppFieldHero(
      icon: real == true ? Icons.graphic_eq : Icons.headphones_outlined,
      eyebrow: 'Escucha en directo',
      title: state,
      subtitle: subtitle,
      status: AppStatusPill(
        text: real == true ? 'En vivo' : _statusLabel(desired),
        icon: real == true
            ? Icons.radio_button_checked
            : Icons.power_settings_new,
        color: _stateColor(desired, real),
      ),
      child: AppSoundBars(
        active: real == true,
        height: 64,
        color: _stateColor(desired, real),
      ),
    );
  }

  Widget _buildControls() {
    final disabled = changingStream || loadingStatus;
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
    final shouldStop = desired == true || real == true;

    return AppDataPanel(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Control de escucha',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 12),
          ElevatedButton.icon(
            onPressed: disabled ? null : () => _setStream(!shouldStop),
            icon: Icon(shouldStop ? Icons.stop : Icons.play_arrow),
            label: Text(shouldStop ? 'Detener escucha' : 'Activar escucha'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: disabled ? null : _connectPlayer,
            icon: const Icon(Icons.speaker),
            label: const Text('Conectar reproductor'),
          ),
          if (changingStream) ...[
            const SizedBox(height: 16),
            const Center(child: CircularProgressIndicator()),
          ],
          const SizedBox(height: 10),
          Text(
            kIsWeb
                ? 'En web puedes activar el nodo; la reproduccion HLS depende del navegador.'
                : 'El reproductor usa la salida HLS configurada para la estacion.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  Widget _buildStateDetails() {
    if (loadingStatus) return const SizedBox.shrink();

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

    return AppMetricGrid(
      children: [
        AppMetricCard(
          icon: Icons.power_settings_new,
          label: 'Peticion',
          value: _statusLabel(desired),
          detail: 'Orden enviada al backend',
        ),
        AppMetricCard(
          icon: Icons.sensors,
          label: 'Nodo',
          value: _statusLabel(real),
          detail: real == true ? 'Audio en curso' : 'Sin audio confirmado',
        ),
      ],
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

  Widget _buildContent() {
    return AppPage(
      children: [
        AppHeaderPanel(
          icon: Icons.headphones,
          title: 'Escucha en directo',
          subtitle: 'Nodo: ${widget.nodeName}',
          trailing: IconButton(
            tooltip: 'Actualizar estado',
            onPressed: _loadStatus,
            icon: const Icon(Icons.refresh),
          ),
        ),
        _buildListeningHero(),
        _buildStateDetails(),
        _buildControls(),
        _buildError(),
        _buildPlayerNotice(),
        if (_showPlayerSection) ...[
          const AppSectionTitle(title: 'Reproductor'),
          _buildPlayer(),
        ],
        _buildEndpointCard(),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return _buildContent();
  }
}