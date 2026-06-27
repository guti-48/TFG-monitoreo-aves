enum DetectionReviewStatus { unreviewed, validated, doubtful, discarded }

extension DetectionReviewStatusLabel on DetectionReviewStatus {
  String get storageValue {
    switch (this) {
      case DetectionReviewStatus.validated:
        return 'validated';
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
      case 'doubtful':
        return DetectionReviewStatus.doubtful;
      case 'discarded':
        return DetectionReviewStatus.discarded;
      default:
        return DetectionReviewStatus.unreviewed;
    }
  }
}
