import 'package:birdmonitor_app/main.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('shows connection screen when no backend is saved', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});

    await tester.pumpWidget(const BirdMonitorApp());
    await tester.pumpAndSettle();

    expect(find.text('Conexión'), findsOneWidget);
    expect(find.text('Servidor FastAPI'), findsOneWidget);
  });
}