import 'package:flutter/material.dart';

import 'summary_screen.dart';
import 'detections_screen.dart';
import 'live_stream_screen.dart';
import 'nodes_screen.dart';

class MainNavigationScreen extends StatefulWidget {
  final String baseUrl;

  const MainNavigationScreen({
    super.key,
    required this.baseUrl,
  });

  @override
  State<MainNavigationScreen> createState() => _MainNavigationScreenState();
}

class _MainNavigationScreenState extends State<MainNavigationScreen> {
  int _selectedIndex = 0;

  late final List<Widget> _screens = [
    SummaryScreen(baseUrl: widget.baseUrl),
    DetectionsScreen(baseUrl: widget.baseUrl),
    LiveStreamScreen(baseUrl: widget.baseUrl),
    NodesScreen(baseUrl: widget.baseUrl),
  ];

  final List<String> _titles = [
    'Resumen',
    'Detecciones',
    'Escucha',
    'Nodos',
  ];

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_selectedIndex]),
      ),
      body: _screens[_selectedIndex],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: _onItemTapped,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Resumen',
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
            icon: Icon(Icons.memory_outlined),
            selectedIcon: Icon(Icons.memory),
            label: 'Nodos',
        ),
        ],
      ),
    );
  }
}