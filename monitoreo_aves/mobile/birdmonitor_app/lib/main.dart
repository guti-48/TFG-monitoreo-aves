import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/connection_screen.dart';
import 'screens/home_screen.dart';

void main() {
  runApp(const BirdMonitorApp());
}

class BirdMonitorApp extends StatelessWidget {
  const BirdMonitorApp({super.key});

  Future<String?> _loadBackendUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('backend_url');
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BirdMonitor',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: Colors.green,
      ),
      home: FutureBuilder<String?>(
        future: _loadBackendUrl(),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          }

          final savedUrl = snapshot.data;

          if (savedUrl == null || savedUrl.isEmpty) {
            return const ConnectionScreen();
          }

          return HomeScreen(baseUrl: savedUrl);
        },
      ),
    );
  }
}