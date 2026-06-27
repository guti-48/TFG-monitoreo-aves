import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/connection_screen.dart';
import 'screens/main_navigation_screen.dart';

const _bgBase = Color(0xFFF4F6F1);
const _bgSurface = Color(0xFFFFFFFF);
const _borderSubtle = Color(0xFFDDE3D8);
const _green = Color(0xFF2F6F4E);
const _greenStrong = Color(0xFF22543A);
const _greenSoft = Color(0xFFE4EEE5);
const _textPrimary = Color(0xFF1F2923);
const _textSecondary = Color(0xFF5F6F65);

void main() {
  runApp(const BirdMonitorApp());
}

class BirdMonitorApp extends StatelessWidget {
  const BirdMonitorApp({super.key});

  Future<String?> _loadBackendUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('backend_url');
  }

  ThemeData _buildTheme() {
    final colorScheme =
        ColorScheme.fromSeed(
          seedColor: _green,
          brightness: Brightness.light,
        ).copyWith(
          primary: _green,
          onPrimary: Colors.white,
          secondary: const Color(0xFF326F72),
          surface: _bgSurface,
          surfaceContainerHighest: _greenSoft,
          error: const Color(0xFF9C3F3F),
          onSurface: _textPrimary,
          onSurfaceVariant: _textSecondary,
        );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: _bgBase,
      appBarTheme: const AppBarTheme(
        backgroundColor: _bgSurface,
        foregroundColor: _textPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: _textPrimary,
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
        shape: Border(bottom: BorderSide(color: _borderSubtle)),
      ),
      cardTheme: CardThemeData(
        color: _bgSurface,
        elevation: 0,
        margin: const EdgeInsets.only(bottom: 10),
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: const BorderSide(color: _borderSubtle),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: _bgSurface,
        elevation: 0,
        indicatorColor: _greenSoft,
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return TextStyle(
            color: selected ? _greenStrong : _textSecondary,
            fontSize: 12,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
          );
        }),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return IconThemeData(
            color: selected ? _greenStrong : _textSecondary,
            size: 24,
          );
        }),
      ),
      listTileTheme: const ListTileThemeData(
        iconColor: _green,
        titleTextStyle: TextStyle(
          color: _textPrimary,
          fontSize: 15,
          fontWeight: FontWeight.w700,
        ),
        subtitleTextStyle: TextStyle(
          color: _textSecondary,
          fontSize: 13,
          height: 1.35,
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          foregroundColor: _textSecondary,
          hoverColor: _greenSoft,
          focusColor: _greenSoft,
          highlightColor: _greenSoft,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: _green,
          foregroundColor: Colors.white,
          elevation: 0,
          minimumSize: const Size.fromHeight(46),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: _green,
          minimumSize: const Size.fromHeight(46),
          side: const BorderSide(color: Color(0xFFC6D0C2)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: _bgSurface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: _borderSubtle),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: _borderSubtle),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: _green, width: 1.4),
        ),
      ),
      textTheme: const TextTheme(
        titleLarge: TextStyle(
          color: _textPrimary,
          fontSize: 20,
          fontWeight: FontWeight.w800,
        ),
        titleMedium: TextStyle(
          color: _textPrimary,
          fontSize: 16,
          fontWeight: FontWeight.w800,
        ),
        bodyMedium: TextStyle(color: _textPrimary, fontSize: 14, height: 1.4),
        bodySmall: TextStyle(color: _textSecondary, fontSize: 12, height: 1.35),
      ),
      dividerTheme: const DividerThemeData(color: _borderSubtle, thickness: 1),
      progressIndicatorTheme: const ProgressIndicatorThemeData(color: _green),
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BirdMonitor',
      debugShowCheckedModeBanner: false,
      theme: _buildTheme(),
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

          return MainNavigationScreen(baseUrl: savedUrl);
        },
      ),
    );
  }
}