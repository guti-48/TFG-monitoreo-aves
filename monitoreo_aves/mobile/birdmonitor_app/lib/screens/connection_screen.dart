import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/api_service.dart';
import 'main_navigation_screen.dart';

class ConnectionScreen extends StatefulWidget {
  const ConnectionScreen({super.key});

  @override
  State<ConnectionScreen> createState() => _ConnectionScreenState();
}

class _ConnectionScreenState extends State<ConnectionScreen> {
  final TextEditingController _controller = TextEditingController();

  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadSavedUrl();
  }

  Future<void> _loadSavedUrl() async {
    final prefs = await SharedPreferences.getInstance();
    final savedUrl = prefs.getString('backend_url');

    if (savedUrl != null && savedUrl.isNotEmpty) {
      _controller.text = savedUrl;
    }
  }

  Future<void> _testConnection() async {
    FocusScope.of(context).unfocus();

    setState(() {
      _loading = true;
      _error = null;
    });

    var url = _controller.text.trim();

    if (url.isEmpty) {
      setState(() {
        _loading = false;
        _error = 'Introduce la URL del backend';
      });
      return;
    }

    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'http://$url';
    }

    if (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }

    final api = ApiService(url);
    final ok = await api.testConnection();

    if (!mounted) return;

    setState(() {
      _loading = false;
    });

    if (!ok) {
      setState(() {
        _error = 'No se pudo conectar con el backend';
      });
      return;
    }

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('backend_url', url);

    if (!mounted) return;

    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (_) => MainNavigationScreen(baseUrl: url),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('BirdMonitor'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: ListView(
          children: [
            const Text(
              'Conexión con BirdMonitor',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              'Introduce la URL del backend FastAPI. Debe ser la IP LAN o Tailscale del servidor, no 127.0.0.1 si usas móvil real.',
            ),
            const SizedBox(height: 20),
            TextField(
              controller: _controller,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(
                labelText: 'URL del backend',
                hintText: 'http://192.168.1.45:8000',
                border: OutlineInputBorder(),
              ),
              onSubmitted: (_) => _testConnection(),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loading ? null : _testConnection,
              child: _loading
                  ? const SizedBox(
                      height: 22,
                      width: 22,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Probar conexión'),
            ),
            if (_error != null) ...[
              const SizedBox(height: 16),
              Text(
                _error!,
                style: const TextStyle(color: Colors.red),
              ),
            ],
          ],
        ),
      ),
    );
  }
}