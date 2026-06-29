import 'package:flutter/material.dart';
import 'package:video_player/video_player.dart';

import '../models/detection.dart';
import '../models/review_status.dart';
import '../services/api_service.dart';
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
  late final TextEditingController _noteController;
  late final TextEditingController _correctedSpeciesController;
  late Future<List<String>> _speciesOptionsFuture;
  VideoPlayerController? _audioController;
  bool loadingAudio = false;
  bool loadingReview = false;
  bool savingReview = false;
  String? audioError;
  DetectionReviewStatus reviewStatus = DetectionReviewStatus.unreviewed;

  @override
  void initState() {
    super.initState();
    api = ApiService(widget.baseUrl);
    _noteController = TextEditingController();
    _correctedSpeciesController = TextEditingController();
    _speciesOptionsFuture = _loadSpeciesOptions();
    _loadReviewFromDetection();
  }

  @override
  void dispose() {
    _audioController?.removeListener(_onAudioChanged);
    _audioController?.dispose();
    _noteController.dispose();
    _correctedSpeciesController.dispose();
    super.dispose();
  }

  void _onAudioChanged() {
    if (mounted) setState(() {});
  }

  String get _filename => widget.detection.filename?.trim() ?? '';

  String get _displaySpecies {
    if (reviewStatus == DetectionReviewStatus.noise) {
      return 'Ruido ambiente';
    }

    final correctedSpecies = _correctedSpeciesController.text.trim();
    if (reviewStatus == DetectionReviewStatus.corrected &&
        correctedSpecies.isNotEmpty) {
      return correctedSpecies;
    }

    return widget.detection.species;
  }

  Future<List<String>> _loadSpeciesOptions() async {
    try {
      return await api.getSpeciesOptions();
    } catch (_) {
      return [];
    }
  }

  void _loadReviewFromDetection() {
    final review = widget.detection.review;

    reviewStatus = widget.detection.reviewStatus;
    _noteController.text = review?.note ?? '';
    _correctedSpeciesController.text = review?.correctedSpecies ?? '';
  }

  Future<void> _setReviewStatus(DetectionReviewStatus status) async {
    final correctedSpecies = _correctedSpeciesController.text.trim();

    if (status == DetectionReviewStatus.corrected && correctedSpecies.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Indica la especie corregida')),
      );
      return;
    }

    setState(() {
      savingReview = true;
    });

    try {
      final review = await api.updateDetectionReview(
        detectionId: widget.detection.id,
        status: status,
        correctedSpecies: status == DetectionReviewStatus.corrected
            ? correctedSpecies
            : null,
        note: _noteController.text,
      );

      if (!mounted) return;

      setState(() {
        reviewStatus = review.status;
        _noteController.text = review.note ?? '';
        _correctedSpeciesController.text = review.correctedSpecies ?? '';
        savingReview = false;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Revision guardada: ${review.status.label}')),
      );
    } catch (e) {
      if (!mounted) return;

      setState(() {
        savingReview = false;
      });

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('No se pudo guardar: $e')));
    }
  }

  Future<void> _saveNote() async {
    if (reviewStatus == DetectionReviewStatus.corrected &&
        _correctedSpeciesController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Indica la especie corregida')),
      );
      return;
    }

    setState(() {
      savingReview = true;
    });

    try {
      final review = await api.updateDetectionReview(
        detectionId: widget.detection.id,
        status: reviewStatus,
        correctedSpecies: reviewStatus == DetectionReviewStatus.corrected
            ? _correctedSpeciesController.text
            : null,
        note: _noteController.text,
      );

      if (!mounted) return;

      setState(() {
        reviewStatus = review.status;
        _noteController.text = review.note ?? '';
        _correctedSpeciesController.text = review.correctedSpecies ?? '';
        savingReview = false;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Revision guardada en backend')),
      );
    } catch (e) {
      if (!mounted) return;

      setState(() {
        savingReview = false;
      });

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('No se pudo guardar: $e')));
    }
  }

  IconData _reviewIcon(DetectionReviewStatus status) {
    switch (status) {
      case DetectionReviewStatus.validated:
        return Icons.check_circle_outline;
      case DetectionReviewStatus.corrected:
        return Icons.edit_outlined;
      case DetectionReviewStatus.noise:
        return Icons.volume_off_outlined;
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
      case DetectionReviewStatus.corrected:
        return Theme.of(context).colorScheme.secondary;
      case DetectionReviewStatus.noise:
        return const Color(0xFF8A6A2A);
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

    return AppFieldHero(
      icon: Icons.pets,
      eyebrow: 'Evidencia de campo',
      title: _displaySpecies,
      subtitle:
          '${confidenceLabel(detection.confidence)} - ${formatConfidence(detection.confidence)}'
          '${reviewStatus == DetectionReviewStatus.corrected ? ' - Original: ${detection.species}' : ''}',
      status: AppStatusPill(
        text: loadingReview
            ? formatConfidence(detection.confidence)
            : reviewStatus.label,
        icon: loadingReview ? Icons.verified : _reviewIcon(reviewStatus),
        color: loadingReview ? null : _reviewColor(reviewStatus),
      ),
      child: AppSoundBars(
        active: reviewStatus != DetectionReviewStatus.discarded,
        height: 42,
        color: _reviewColor(reviewStatus),
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
              height: 240,
              fit: BoxFit.cover,
              loadingBuilder: (context, child, progress) {
                if (progress == null) return child;
                return const SizedBox(
                  height: 240,
                  child: Center(child: CircularProgressIndicator()),
                );
              },
              errorBuilder: (context, error, stackTrace) {
                return Container(
                  height: 220,
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
          const SizedBox(height: 8),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Ruta del espectrograma'),
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: SelectableText(
                  url,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ],
          ),
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
          const SizedBox(height: 8),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Ruta del archivo WAV'),
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: SelectableText(
                  url,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ],
          ),
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
      padding: EdgeInsets.zero,
      child: ExpansionTile(
        leading: const Icon(Icons.tune_outlined),
        title: const Text('Detalles tecnicos'),
        subtitle: const Text('Archivo, fecha, amplitud e identificadores'),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        children: [
          for (final entry in rows.entries) ...[
            AppDetailRow(
              icon: Icons.chevron_right,
              label: entry.key,
              value: entry.value,
            ),
            if (entry.key != rows.keys.last) const SizedBox(height: 8),
          ],
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
                  'Revision del registro',
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
              _buildReviewButton(DetectionReviewStatus.noise),
              _buildReviewButton(DetectionReviewStatus.corrected),
              _buildReviewButton(DetectionReviewStatus.doubtful),
              _buildReviewButton(DetectionReviewStatus.discarded),
              _buildReviewButton(DetectionReviewStatus.unreviewed),
            ],
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _correctedSpeciesController,
            enabled: !savingReview,
            decoration: const InputDecoration(
              labelText: 'Especie corregida',
              hintText: 'Solo si no coincide con la prediccion original',
              prefixIcon: Icon(Icons.edit_outlined),
            ),
          ),
          const SizedBox(height: 8),
          FutureBuilder<List<String>>(
            future: _speciesOptionsFuture,
            builder: (context, snapshot) {
              final options = (snapshot.data ?? [])
                  .where((species) => species != widget.detection.species)
                  .take(8)
                  .toList();

              if (options.isEmpty) return const SizedBox.shrink();

              return Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final species in options)
                    ActionChip(
                      label: Text(species),
                      onPressed: savingReview
                          ? null
                          : () {
                              setState(() {
                                _correctedSpeciesController.text = species;
                              });
                            },
                    ),
                ],
              );
            },
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
            'La revision se guarda en el backend y queda visible tambien en el dashboard.',
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
            subtitle: 'Primero escucha y mira; despues decide la revision.',
          ),
          _buildSpectrogram(),
          _buildAudio(),
          const AppSectionTitle(
            title: 'Revision',
            subtitle: 'Marca si es correcta, ruido o necesita correccion.',
          ),
          _buildReviewPanel(),
          _buildTechnicalData(),
        ],
      ),
    );
  }
}