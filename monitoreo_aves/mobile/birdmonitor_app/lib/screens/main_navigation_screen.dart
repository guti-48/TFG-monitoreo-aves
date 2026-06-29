import 'package:flutter/material.dart';

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

  late final List<Widget> _screens = [
    SummaryScreen(baseUrl: widget.baseUrl),
    DetectionsScreen(baseUrl: widget.baseUrl),
    LiveStreamScreen(baseUrl: widget.baseUrl),
    EcologyScreen(baseUrl: widget.baseUrl),
  ];

  final List<String> _titles = ['Inicio', 'Detecciones', 'Escucha', 'Analisis'];

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  void _openScreen(Widget screen) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
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
        leading: Padding(
          padding: const EdgeInsets.only(left: 16, top: 10, bottom: 10),
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.primaryContainer,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Center(child: BirdMonitorLogo(size: 25)),
          ),
        ),
        titleSpacing: 12,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('BirdMonitor'),
            Text(
              _titles[_selectedIndex],
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
        actions: [
          PopupMenuButton<String>(
            tooltip: 'Menu',
            icon: const Icon(Icons.more_vert),
            onSelected: (value) {
              switch (value) {
                case 'daily':
                  _openScreen(DailyReportScreen(baseUrl: widget.baseUrl));
                  break;
                case 'stations':
                  _openScreen(NodesScreen(baseUrl: widget.baseUrl));
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
