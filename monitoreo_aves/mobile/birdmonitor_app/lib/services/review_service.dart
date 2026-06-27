import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/review_status.dart';

class ReviewService {
  static const _statusKey = 'birdmonitor_detection_review_statuses_v1';
  static const _noteKey = 'birdmonitor_detection_review_notes_v1';

  Future<Map<int, DetectionReviewStatus>> getStatuses() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_statusKey);

    if (raw == null || raw.isEmpty) return {};

    final decoded = jsonDecode(raw);
    if (decoded is! Map<String, dynamic>) return {};

    return decoded.map((key, value) {
      final id = int.tryParse(key) ?? 0;
      return MapEntry(
        id,
        DetectionReviewStatusLabel.fromStorage(value?.toString()),
      );
    })..removeWhere((key, value) => key <= 0);
  }

  Future<DetectionReviewStatus> getStatus(int detectionId) async {
    final statuses = await getStatuses();
    return statuses[detectionId] ?? DetectionReviewStatus.unreviewed;
  }

  Future<void> setStatus(int detectionId, DetectionReviewStatus status) async {
    final prefs = await SharedPreferences.getInstance();
    final statuses = await getStatuses();

    if (status == DetectionReviewStatus.unreviewed) {
      statuses.remove(detectionId);
    } else {
      statuses[detectionId] = status;
    }

    await prefs.setString(
      _statusKey,
      jsonEncode(
        statuses.map(
          (key, value) => MapEntry(key.toString(), value.storageValue),
        ),
      ),
    );
  }

  Future<Map<int, String>> getNotes() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_noteKey);

    if (raw == null || raw.isEmpty) return {};

    final decoded = jsonDecode(raw);
    if (decoded is! Map<String, dynamic>) return {};

    return decoded.map((key, value) {
      final id = int.tryParse(key) ?? 0;
      return MapEntry(id, value?.toString() ?? '');
    })..removeWhere((key, value) => key <= 0 || value.trim().isEmpty);
  }

  Future<String> getNote(int detectionId) async {
    final notes = await getNotes();
    return notes[detectionId] ?? '';
  }

  Future<void> setNote(int detectionId, String note) async {
    final prefs = await SharedPreferences.getInstance();
    final notes = await getNotes();
    final cleanNote = note.trim();

    if (cleanNote.isEmpty) {
      notes.remove(detectionId);
    } else {
      notes[detectionId] = cleanNote;
    }

    await prefs.setString(
      _noteKey,
      jsonEncode(notes.map((key, value) => MapEntry(key.toString(), value))),
    );
  }
}