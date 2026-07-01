import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'daily_report_screen.dart';
import 'detections_screen.dart';
import 'ecology_screen.dart';
import 'live_stream_screen.dart';
import 'nodes_screen.dart';
import 'settings_screen.dart';
import 'summary_screen.dart';
import '../widgets/app_ui.dart';

class MainNavigationScreen extends StatefulWidget {
  final String baseUrl;

  const MainNavigationScreen({super.key, required this.baseUrl});

  @override
  State<MainNavigationScreen> createState() => _MainNavigationScreenState();
}

class _MainNavigationScreenState extends State<MainNavigationScreen> {
  int _selectedIndex = 0;
  final List<int> _refreshTokens = [0, 0, 0, 0];

  static const List<String> _titles = [
    'Inicio',
    'Detecciones',
    'Escucha',
    'Analisis',
  ];

  List<Widget> get _screens => [
    SummaryScreen(
      key: ValueKey('summary-${_refreshTokens[0]}'),
      baseUrl: widget.baseUrl,
    ),
    DetectionsScreen(
      key: ValueKey('detections-${_refreshTokens[1]}'),
      baseUrl: widget.baseUrl,
    ),
    LiveStreamScreen(
      key: ValueKey('stream-${_refreshTokens[2]}'),
      baseUrl: widget.baseUrl,
    ),
    EcologyScreen(
      key: ValueKey('ecology-${_refreshTokens[3]}'),
      baseUrl: widget.baseUrl,
    ),
  ];

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  void _openSecondaryScreen(String title, Widget screen) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => AppSecondaryScaffold(title: title, child: screen),
      ),
    );
  }

  void _openScreen(Widget screen) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
  }

  void _refreshCurrentTab() {
    setState(() {
      _refreshTokens[_selectedIndex]++;
    });
  }

  void _showAbout() {
    showAboutDialog(
      context: context,
      applicationName: 'BirdMonitor App',
      applicationVersion: '1.0.0',
      applicationIcon: const BirdMonitorLogo(size: 42),
      children: const [
        Text(
          'Cliente movil para detecciones, escucha en directo y analisis bioacustico de campo.',
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 72,
        centerTitle: true,
        backgroundColor: Theme.of(context).colorScheme.primary,
        foregroundColor: Colors.white,
        systemOverlayStyle: SystemUiOverlayStyle.light,
        shape: const Border(bottom: BorderSide(color: Color(0xFF22543A))),
        leadingWidth: 72,
        leading: PopupMenuButton<String>(
          tooltip: 'Opciones',
          icon: const Icon(Icons.settings_outlined, color: Colors.white),
          onSelected: (value) {
            switch (value) {
              case 'daily':
                _openSecondaryScreen(
                  'Informe diario',
                  DailyReportScreen(baseUrl: widget.baseUrl),
                );
                break;
              case 'stations':
                _openSecondaryScreen(
                  'Estaciones',
                  NodesScreen(baseUrl: widget.baseUrl),
                );
                break;
              case 'settings':
                _openScreen(SettingsScreen(baseUrl: widget.baseUrl));
                break;
              case 'about':
                _showAbout();
                break;
            }
          },
          itemBuilder: (context) => const [
            PopupMenuItem(
              value: 'daily',
              child: ListTile(
                leading: Icon(Icons.today_outlined),
                title: Text('Informe diario'),
              ),
            ),
            PopupMenuItem(
              value: 'stations',
              child: ListTile(
                leading: Icon(Icons.place_outlined),
                title: Text('Estaciones'),
              ),
            ),
            PopupMenuItem(
              value: 'settings',
              child: ListTile(
                leading: Icon(Icons.settings_outlined),
                title: Text('Configuracion'),
              ),
            ),
            PopupMenuItem(
              value: 'about',
              child: ListTile(
                leading: Icon(Icons.info_outline),
                title: Text('Acerca de'),
              ),
            ),
          ],
        ),
        title: _selectedIndex == 0
            ? const BirdMonitorLogo(size: 48)
            : Text(
                _titles[_selectedIndex],
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                ),
              ),
        actions: [
          SizedBox(
            width: 72,
            child: IconButton(
              tooltip: 'Actualizar',
              onPressed: _refreshCurrentTab,
              icon: const Icon(Icons.refresh, color: Colors.white),
            ),
          ),
        ],
      ),
      body: _screens[_selectedIndex],
      bottomNavigationBar: DecoratedBox(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: Color(0xFFDDE3D8))),
        ),
        child: NavigationBar(
          selectedIndex: _selectedIndex,
          onDestinationSelected: _onItemTapped,
          destinations: const [
            NavigationDestination(
              icon: Icon(Icons.dashboard_outlined),
              selectedIcon: Icon(Icons.dashboard),
              label: 'Inicio',
            ),
            NavigationDestination(
              icon: Icon(Icons.list_alt_outlined),
              selectedIcon: Icon(Icons.list_alt),
              label: 'Detecciones',
            ),
            NavigationDestination(
              icon: Icon(Icons.headphones_outlined),
              selectedIcon: Icon(Icons.headphones),
              label: 'Escucha',
            ),
            NavigationDestination(
              icon: Icon(Icons.eco_outlined),
              selectedIcon: Icon(Icons.eco),
              label: 'Analisis',
            ),
          ],
        ),
      ),
    );
  }
}