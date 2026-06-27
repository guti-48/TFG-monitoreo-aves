import 'package:intl/intl.dart';

String formatTimestamp(String? raw) {
  if (raw == null || raw.trim().isEmpty) return 'Sin fecha';

  final parsed = DateTime.tryParse(raw);

  if (parsed == null) return raw;

  return DateFormat('dd/MM/yyyy - HH:mm').format(parsed);
}

String formatDateOnly(DateTime date) {
  return DateFormat('dd/MM/yyyy').format(date);
}

String formatApiDate(DateTime date) {
  return DateFormat('yyyy-MM-dd').format(date);
}

String formatHour(dynamic rawHour) {
  final hour = _toInt(rawHour);

  if (hour < 0 || hour > 23) {
    return rawHour?.toString() ?? '-';
  }

  final start = hour.toString().padLeft(2, '0');
  final end = ((hour + 1) % 24).toString().padLeft(2, '0');

  return '$start:00 - $end:00';
}

String formatValue(dynamic value) {
  if (value == null) return 'Sin datos';

  if (value is List) {
    if (value.isEmpty) return 'Sin especies';
    return value.join(', ');
  }

  if (value is Map) {
    if (value.isEmpty) return 'Sin datos';

    return value.entries
        .map((entry) => '${entry.key}: ${entry.value}')
        .join(' | ');
  }

  if (value is int) {
    return value.toString();
  }

  if (value is double) {
    if (value == value.roundToDouble()) {
      return value.toInt().toString();
    }

    if (value.abs() < 1) {
      return value.toStringAsFixed(4);
    }

    return value.toStringAsFixed(2);
  }

  if (value is String) {
    final parsed = double.tryParse(value);

    if (parsed != null) {
      return formatValue(parsed);
    }

    return value;
  }

  return value.toString();
}

String prettyLabel(String key) {
  switch (key) {
    case 'abundancia':
      return 'Abundancia';
    case 'riqueza':
      return 'Riqueza de especies';
    case 'shannon':
      return 'Índice de Shannon';
    case 'simpson':
      return 'Índice de Simpson';
    case 'pielou':
      return 'Equidad de Pielou';
    case 'calidad':
      return 'Calidad ecológica';
    case 'zona':
      return 'Zona';

    case 'rms':
      return 'RMS';
    case 'aci':
      return 'ACI';
    case 'adi':
      return 'ADI';
    case 'aei':
      return 'AEI';
    case 'bio':
      return 'BIO';
    case 'ndsi':
      return 'NDSI';
    case 'ht':
      return 'HT';
    case 'hf':
      return 'HF';
    case 'h':
      return 'H';

    case 'rms_avg':
      return 'RMS medio';
    case 'aci_avg':
      return 'ACI medio';
    case 'adi_avg':
      return 'ADI medio';
    case 'aei_avg':
      return 'AEI medio';
    case 'bio_avg':
      return 'BIO medio';
    case 'ndsi_avg':
      return 'NDSI medio';
    case 'ht_avg':
      return 'HT medio';
    case 'hf_avg':
      return 'HF medio';
    case 'h_avg':
      return 'H medio';

    case 'hour':
    case 'hora':
    case 'h_hour':
      return 'Hora';

    case 'total_detecciones':
    case 'detections':
    case 'num_detections':
    case 'count':
    case 'total':
      return 'Total de detecciones';

    case 'confianza_media':
    case 'avg_confidence':
    case 'confidence_avg':
      return 'Confianza media';

    case 'especies_activas':
    case 'active_species':
    case 'species_count':
      return 'Especies activas';

    case 'lista_especies':
    case 'species':
    case 'especies':
      return 'Lista de especies';

    case 'filename':
      return 'Archivo';
    case 'timestamp':
      return 'Fecha y hora';

    default:
      return key
          .replaceAll('_', ' ')
          .replaceFirstMapped(
            RegExp(r'^[a-zA-Z]'),
            (match) => match.group(0)!.toUpperCase(),
          );
  }
}

String formatFilename(String? filename) {
  if (filename == null || filename.trim().isEmpty) {
    return 'Sin archivo asociado';
  }

  return filename;
}

double confidencePercent(double confidence) {
  return confidence <= 1 ? confidence * 100 : confidence;
}

String formatConfidence(double confidence) {
  return '${confidencePercent(confidence).toStringAsFixed(1)}%';
}

String confidenceLabel(double confidence) {
  final value = confidencePercent(confidence);

  if (value >= 80) return 'Alta confianza';
  if (value >= 60) return 'Confianza media';
  return 'Revision recomendada';
}

int _toInt(dynamic value) {
  if (value is int) return value;
  if (value is double) return value.toInt();
  if (value is String) return int.tryParse(value) ?? -1;
  return -1;
}