enum DetectionReviewStatus {
  unreviewed,
  validated,
  corrected,
  noise,
  doubtful,
  discarded,
}

extension DetectionReviewStatusLabel on DetectionReviewStatus {
  String get storageValue {
    switch (this) {
      case DetectionReviewStatus.validated:
        return 'validated';
      case DetectionReviewStatus.corrected:
        return 'corrected';
      case DetectionReviewStatus.noise:
        return 'noise';
      case DetectionReviewStatus.doubtful:
        return 'doubtful';
      case DetectionReviewStatus.discarded:
        return 'discarded';
      case DetectionReviewStatus.unreviewed:
        return 'unreviewed';
    }
  }

  String get label {
    switch (this) {
      case DetectionReviewStatus.validated:
        return 'Validada';
      case DetectionReviewStatus.corrected:
        return 'Corregida';
      case DetectionReviewStatus.noise:
        return 'Ruido ambiente';
      case DetectionReviewStatus.doubtful:
        return 'Dudosa';
      case DetectionReviewStatus.discarded:
        return 'Descartada';
      case DetectionReviewStatus.unreviewed:
        return 'Sin revisar';
    }
  }

  String get actionLabel {
    switch (this) {
      case DetectionReviewStatus.validated:
        return 'Validar';
      case DetectionReviewStatus.corrected:
        return 'Corregir especie';
      case DetectionReviewStatus.noise:
        return 'Ruido';
      case DetectionReviewStatus.doubtful:
        return 'Marcar duda';
      case DetectionReviewStatus.discarded:
        return 'Descartar';
      case DetectionReviewStatus.unreviewed:
        return 'Quitar revision';
    }
  }

  static DetectionReviewStatus fromStorage(String? value) {
    switch (value) {
      case 'validated':
        return DetectionReviewStatus.validated;
      case 'corrected':
        return DetectionReviewStatus.corrected;
      case 'noise':
        return DetectionReviewStatus.noise;
      case 'doubtful':
        return DetectionReviewStatus.doubtful;
      case 'discarded':
        return DetectionReviewStatus.discarded;
      default:
        return DetectionReviewStatus.unreviewed;
    }
  }
}
