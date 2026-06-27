import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../models/detection.dart';
import '../models/review_status.dart';
import '../services/api_service.dart';
import '../services/review_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_ui.dart';

class DetectionDetailScreen extends StatefulWidget {
  final Detection detection;
  final String baseUrl;

  const DetectionDetailScreen({
    super.key,
    required this.detection,
    required this.baseUrl,
  });

  @override
  State<DetectionDetailScreen> createState() => _DetectionDetailScreenState();
}

class _DetectionDetailScreenState extends State<DetectionDetailScreen> {
  late final ApiService api;
  late final ReviewService reviewService;
  late final TextEditingController _noteController;
  VideoPlayerController? _audioController;
  bool loadingAudio = false;
  bool loadingReview = true;
  bool savingReview = false;
  String? audioError;
  DetectionReviewStatus reviewStatus = DetectionReviewStatus.unreviewed;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    reviewService = ReviewService();
    _noteController = TextEditingController();
    _loadReview();
  }

  @override
  void dispose() {
    _audioController?.removeListener(_onAudioChanged);
    _audioController?.dispose();
    _noteController.dispose();
    super.dispose();
  }

  void _onAudioChanged() {
    if (mounted) setState(() {});
  }

  String get _filename => widget.detection.filename?.trim() ?? '';

  Future<void> _loadReview() async {
    final status = await reviewService.getStatus(widget.detection.id);
    final note = await reviewService.getNote(widget.detection.id);

    if (!mounted) return;

    setState(() {
      reviewStatus = status;
      _noteController.text = note;
      loadingReview = false;
    });
  }

  Future<void> _setReviewStatus(DetectionReviewStatus status) async {
    setState(() {
      savingReview = true;
    });

    await reviewService.setStatus(widget.detection.id, status);

    if (!mounted) return;

    setState(() {
      reviewStatus = status;
      savingReview = false;
    });

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Revision guardada: ${status.label}')),
    );
  }

  Future<void> _saveNote() async {
    setState(() {
      savingReview = true;
    });

    await reviewService.setNote(widget.detection.id, _noteController.text);

    if (!mounted) return;

    setState(() {
      savingReview = false;
    });

    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('Nota de revision guardada')));
  }

  IconData _reviewIcon(DetectionReviewStatus status) {
    switch (status) {
      case DetectionReviewStatus.validated:
        return Icons.check_circle_outline;
      case DetectionReviewStatus.doubtful:
        return Icons.help_outline;
      case DetectionReviewStatus.discarded:
        return Icons.cancel_outlined;
      case DetectionReviewStatus.unreviewed:
        return Icons.rate_review_outlined;
    }
  }

  Color _reviewColor(DetectionReviewStatus status) {
    switch (status) {
      case DetectionReviewStatus.validated:
        return Theme.of(context).colorScheme.primary;
      case DetectionReviewStatus.doubtful:
        return const Color(0xFF9A6A1E);
      case DetectionReviewStatus.discarded:
        return Theme.of(context).colorScheme.error;
      case DetectionReviewStatus.unreviewed:
        return Theme.of(context).colorScheme.secondary;
    }
  }

  Future<void> _loadAudio() async {
    if (_filename.isEmpty) return;

    setState(() {
      loadingAudio = true;
      audioError = null;
    });

    try {
      _audioController?.removeListener(_onAudioChanged);
      await _audioController?.dispose();

      final controller = VideoPlayerController.networkUrl(
        Uri.parse(api.getAudioUrl(_filename)),
      );
      controller.addListener(_onAudioChanged);
      await controller.initialize();

      if (!mounted) {
        await controller.dispose();
        return;
      }

      setState(() {
        _audioController = controller;
        loadingAudio = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        loadingAudio = false;
        audioError = e.toString();
      });
    }
  }

  Future<void> _toggleAudio() async {
    final controller = _audioController;

    if (controller == null || !controller.value.isInitialized) {
      await _loadAudio();
      await _audioController?.play();
      return;
    }

    if (controller.value.isPlaying) {
      await controller.pause();
    } else {
      await controller.play();
    }
  }

  Widget _buildHero() {
    final detection = widget.detection;

    return AppHeaderPanel(
      icon: Icons.pets,
      title: detection.species,
      subtitle:
          '${confidenceLabel(detection.confidence)} - ${formatConfidence(detection.confidence)}',
      trailing: AppStatusPill(
        text: loadingReview
            ? formatConfidence(detection.confidence)
            : reviewStatus.label,
        icon: loadingReview ? Icons.verified : _reviewIcon(reviewStatus),
        color: loadingReview ? null : _reviewColor(reviewStatus),
      ),
    );
  }

  Widget _buildSpectrogram() {
    if (_filename.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay espectrograma asociado a esta deteccion.'),
      );
    }

    final url = api.getSpectrogramUrl(_filename);

    return AppDataPanel(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Espectrograma', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: Image.network(
              url,
              fit: BoxFit.cover,
              loadingBuilder: (context, child, progress) {
                if (progress == null) return child;
                return const SizedBox(
                  height: 180,
                  child: Center(child: CircularProgressIndicator()),
                );
              },
              errorBuilder: (context, error, stackTrace) {
                return Container(
                  height: 180,
                  color: appPanelMuted,
                  alignment: Alignment.center,
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    'No se pudo cargar el PNG del espectrograma.',
                    style: Theme.of(context).textTheme.bodyMedium,
                    textAlign: TextAlign.center,
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 10),
          SelectableText(url, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }

  Widget _buildAudio() {
    if (_filename.isEmpty) {
      return const AppDataPanel(
        padding: EdgeInsets.all(16),
        child: Text('No hay audio asociado a esta deteccion.'),
      );
    }

    final controller = _audioController;
    final initialized = controller != null && controller.value.isInitialized;
    final playing = initialized && controller.value.isPlaying;
    final url = api.getAudioUrl(_filename);

    return AppDataPanel(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Audio WAV',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              FilledButton.tonalIcon(
                onPressed: loadingAudio ? null : _toggleAudio,
                icon: loadingAudio
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Icon(playing ? Icons.pause : Icons.play_arrow),
                label: Text(playing ? 'Pausar' : 'Reproducir'),
              ),
            ],
          ),
          if (initialized) ...[
            const SizedBox(height: 12),
            VideoProgressIndicator(
              controller,
              allowScrubbing: true,
              colors: VideoProgressColors(
                playedColor: Theme.of(context).colorScheme.primary,
                bufferedColor: appGreenSoft,
                backgroundColor: appPanelBorder,
              ),
            ),
          ],
          if (audioError != null) ...[
            const SizedBox(height: 12),
            Text(
              'No se pudo cargar el WAV: $audioError',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          const SizedBox(height: 10),
          SelectableText(url, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }

  Widget _buildTechnicalData() {
    final detection = widget.detection;
    final rows = <String, String>{
      'Fecha': formatTimestamp(detection.timestamp),
      'Archivo': formatFilename(detection.filename),
      'Amplitud': detection.amplitude?.toStringAsFixed(4) ?? 'Sin datos',
      'Dispositivo': detection.deviceId?.toString() ?? 'Sin datos',
      'ID deteccion': detection.id.toString(),
    };

    return AppDataPanel(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Datos tecnicos',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 10),
          for (final entry in rows.entries)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(
                      entry.key,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    flex: 2,
                    child: Text(
                      entry.value,
                      textAlign: TextAlign.end,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildReviewButton(DetectionReviewStatus status) {
    final selected = reviewStatus == status;
    final color = _reviewColor(status);

    return selected
        ? FilledButton.icon(
            onPressed: savingReview ? null : () => _setReviewStatus(status),
            icon: Icon(_reviewIcon(status)),
            label: Text(status.actionLabel),
          )
        : OutlinedButton.icon(
            onPressed: savingReview ? null : () => _setReviewStatus(status),
            icon: Icon(_reviewIcon(status), color: color),
            label: Text(status.actionLabel),
          );
  }

  Widget _buildReviewPanel() {
    if (loadingReview) {
      return const AppDataPanel(
        padding: EdgeInsets.all(24),
        child: Center(child: CircularProgressIndicator()),
      );
    }

    return AppDataPanel(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Estado de revision',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              AppStatusPill(
                text: reviewStatus.label,
                icon: _reviewIcon(reviewStatus),
                color: _reviewColor(reviewStatus),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _buildReviewButton(DetectionReviewStatus.validated),
              _buildReviewButton(DetectionReviewStatus.doubtful),
              _buildReviewButton(DetectionReviewStatus.discarded),
              _buildReviewButton(DetectionReviewStatus.unreviewed),
            ],
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _noteController,
            minLines: 2,
            maxLines: 4,
            decoration: const InputDecoration(
              labelText: 'Nota de revision',
              hintText:
                  'Ejemplo: canto limpio, solape, ruido o duda taxonomica',
              prefixIcon: Icon(Icons.notes_outlined),
            ),
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: savingReview ? null : _saveNote,
            icon: savingReview
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.save_outlined),
            label: const Text('Guardar nota'),
          ),
          const SizedBox(height: 8),
          Text(
            'Guardado localmente en este dispositivo. La sincronizacion con backend puede anadirse cuando exista el endpoint de revision.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Detalle de deteccion')),
      body: AppPage(
        children: [
          _buildHero(),
          const AppSectionTitle(
            title: 'Evidencia acustica',
            subtitle: 'Material disponible para revision humana.',
          ),
          _buildSpectrogram(),
          _buildAudio(),
          const AppSectionTitle(
            title: 'Revision humana',
            subtitle:
                'Valida la prediccion despues de contrastar la evidencia.',
          ),
          _buildReviewPanel(),
          const AppSectionTitle(title: 'Metadatos'),
          _buildTechnicalData(),
        ],
      ),
    );
  }
}