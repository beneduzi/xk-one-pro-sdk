import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

void main() {
  runApp(const XkGlassesExampleApp());
}

class XkGlassesExampleApp extends StatelessWidget {
  const XkGlassesExampleApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'XK Glasses Example',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF004F8F),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        cardTheme: CardThemeData(
          elevation: 2,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        ),
      ),
      home: const GlassesHomeScreen(),
    );
  }
}

class GlassesHomeScreen extends StatefulWidget {
  const GlassesHomeScreen({super.key});

  @override
  State<GlassesHomeScreen> createState() => _GlassesHomeScreenState();
}

class _GlassesHomeScreenState extends State<GlassesHomeScreen> {
  static const _methods = MethodChannel('com.example.xkglasses/methods');
  static const _events = EventChannel('com.example.xkglasses/events');

  StreamSubscription? _eventSubscription;
  List<Map<String, String>> _bondedDevices = [];
  String? _selectedMac;

  String _connectionState = 'IDLE'; // IDLE, CONNECTING, BOUND, PHOTO, ERROR
  int _batteryLevel = -1;
  bool _isCharging = false;
  bool _isLoading = false;

  String? _lastPhotoPath;
  String? _galleryUri;
  String? _statusMessage;

  @override
  void initState() {
    super.initState();
    _loadBondedDevices();
    _subscribeToEvents();
  }

  @override
  void dispose() {
    _eventSubscription?.cancel();
    super.dispose();
  }

  void _subscribeToEvents() {
    _eventSubscription = _events.receiveBroadcastStream().listen((dynamic event) {
      if (event is Map) {
        final type = event['type']?.toString();
        setState(() {
          if (type == 'state') {
            _connectionState = event['state']?.toString() ?? 'IDLE';
            if (_connectionState == 'BOUND') {
              _statusMessage = 'Óculos conectados e prontos!';
            } else if (_connectionState == 'ERROR') {
              _statusMessage = 'Erro na conexão ou timeout.';
            }
          } else if (type == 'battery') {
            _batteryLevel = (event['level'] as num?)?.toInt() ?? -1;
            _isCharging = event['charging'] == true;
          } else if (type == 'button_pressed') {
            _statusMessage = 'Botão dos óculos pressionado! Capturando...';
          } else if (type == 'photo_captured') {
            _lastPhotoPath = event['path']?.toString();
            _galleryUri = event['galleryUri']?.toString();
            _statusMessage = 'Foto salva na Galeria!';
          }
        });
      }
    }, onError: (error) {
      debugPrint('EventChannel error: $error');
    });
  }

  Future<void> _loadBondedDevices() async {
    try {
      final List<dynamic>? devices = await _methods.invokeMethod('getBondedDevices');
      if (devices != null) {
        setState(() {
          _bondedDevices = devices.map((d) => Map<String, String>.from(d as Map)).toList();
          // Pre-select first device matching 'xk' or first available
          if (_selectedMac == null && _bondedDevices.isNotEmpty) {
            final xkDevice = _bondedDevices.firstWhere(
              (d) => (d['name'] ?? '').toLowerCase().contains('xk'),
              orElse: () => _bondedDevices.first,
            );
            _selectedMac = xkDevice['address'];
          }
        });
      }
    } catch (e) {
      debugPrint('Error loading bonded devices: $e');
    }
  }

  Future<void> _connect() async {
    if (_selectedMac == null) return;
    setState(() {
      _isLoading = true;
      _statusMessage = 'Conectando aos óculos...';
    });

    try {
      final bool? ok = await _methods.invokeMethod('connect', {'mac': _selectedMac});
      if (ok == true) {
        setState(() {
          _connectionState = 'BOUND';
          _statusMessage = 'Conectado com sucesso!';
        });
      } else {
        setState(() {
          _connectionState = 'ERROR';
          _statusMessage = 'Falha ao conectar aos óculos.';
        });
      }
    } catch (e) {
      setState(() {
        _connectionState = 'ERROR';
        _statusMessage = 'Erro: $e';
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _disconnect() async {
    try {
      await _methods.invokeMethod('disconnect');
      setState(() {
        _connectionState = 'IDLE';
        _batteryLevel = -1;
        _statusMessage = 'Desconectado.';
      });
    } catch (e) {
      debugPrint('Error disconnecting: $e');
    }
  }

  Future<void> _takePhoto() async {
    if (_connectionState != 'BOUND') return;
    setState(() {
      _isLoading = true;
      _statusMessage = 'Disparando câmera dos óculos e baixando JPEG...';
    });

    try {
      final dynamic result = await _methods.invokeMethod('takePhoto');
      if (result is Map) {
        setState(() {
          _lastPhotoPath = result['path']?.toString();
          _galleryUri = result['galleryUri']?.toString();
          _statusMessage = 'Foto salva na Galeria (Pictures/XKGlasses)!';
        });
      }
    } catch (e) {
      setState(() {
        _statusMessage = 'Erro na captura: $e';
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isConnected = _connectionState == 'BOUND';

    return Scaffold(
      appBar: AppBar(
        title: const Text('XK One Pro · Mini App'),
        centerTitle: true,
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
      ),
      body: RefreshIndicator(
        onRefresh: _loadBondedDevices,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // 1. Connection Card
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(
                            Icons.bluetooth,
                            color: isConnected ? Colors.green : Colors.blueGrey,
                          ),
                          const SizedBox(width: 8),
                          const Text(
                            'Conexão Bluetooth SPP',
                            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                          const Spacer(),
                          _buildStatusChip(),
                        ],
                      ),
                      const SizedBox(height: 16),
                      if (_bondedDevices.isEmpty)
                        const Text(
                          'Nenhum dispositivo Bluetooth pareado encontrado.\nPareie os óculos nas configurações do Android.',
                          style: TextStyle(color: Colors.red),
                        )
                      else
                        DropdownButtonFormField<String>(
                          initialValue: _selectedMac,
                          decoration: const InputDecoration(
                            labelText: 'Dispositivo Pareado',
                            border: OutlineInputBorder(),
                            contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          ),
                          items: _bondedDevices.map((d) {
                            final name = d['name'] ?? 'Desconhecido';
                            final mac = d['address'] ?? '';
                            return DropdownMenuItem(
                              value: mac,
                              child: Text('$name ($mac)'),
                            );
                          }).toList(),
                          onChanged: isConnected
                              ? null
                              : (val) {
                                  setState(() {
                                    _selectedMac = val;
                                  });
                                },
                        ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Expanded(
                            child: ElevatedButton.icon(
                              onPressed: _isLoading
                                  ? null
                                  : isConnected
                                      ? _disconnect
                                      : _connect,
                              icon: _isLoading
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(strokeWidth: 2),
                                    )
                                  : Icon(isConnected ? Icons.link_off : Icons.link),
                              label: Text(isConnected ? 'Desconectar' : 'Conectar aos Óculos'),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: isConnected ? Colors.red.shade100 : Colors.blue.shade100,
                                padding: const EdgeInsets.symmetric(vertical: 12),
                              ),
                            ),
                          ),
                        ],
                      ),
                      if (isConnected && _batteryLevel >= 0) ...[
                        const Divider(height: 24),
                        Row(
                          children: [
                            Icon(
                              _isCharging ? Icons.battery_charging_full : Icons.battery_std,
                              color: _batteryLevel > 20 ? Colors.green : Colors.orange,
                            ),
                            const SizedBox(width: 8),
                            Text(
                              'Nível de Bateria: $_batteryLevel% ${_isCharging ? '(Carregando)' : ''}',
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 16),

              // 2. Action Card
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.camera_alt, color: Colors.indigo),
                          SizedBox(width: 8),
                          Text(
                            'Capturar Imagem',
                            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      const Text(
                        'Pressione o botão abaixo ou aperte o botão físico/toque na haste dos óculos para capturar e salvar na galeria automaticamente.',
                        style: TextStyle(color: Colors.black87),
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton.icon(
                        onPressed: isConnected && !_isLoading ? _takePhoto : null,
                        icon: const Icon(Icons.photo_camera),
                        label: const Text('📸 Tirar e Baixar Foto dos Óculos'),
                        style: ElevatedButton.styleFrom(
                          minimumSize: const Size.fromHeight(48),
                          backgroundColor: Colors.indigo.shade600,
                          foregroundColor: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              if (_statusMessage != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.blueGrey.shade50,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.blueGrey.shade200),
                  ),
                  child: Text(
                    _statusMessage!,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.blueGrey.shade900,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],

              const SizedBox(height: 16),

              // 3. Photo Preview Card
              if (_lastPhotoPath != null && File(_lastPhotoPath!).existsSync()) ...[
                Card(
                  clipBehavior: Clip.antiAlias,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Padding(
                        padding: const EdgeInsets.all(12.0),
                        child: Row(
                          children: [
                            const Icon(Icons.image, color: Colors.green),
                            const SizedBox(width: 8),
                            const Text(
                              'Última Foto Capturada',
                              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                            ),
                            const Spacer(),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: Colors.green.shade100,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: const Text(
                                'Salva na Galeria',
                                style: TextStyle(fontSize: 12, color: Colors.green, fontWeight: FontWeight.bold),
                              ),
                            ),
                          ],
                        ),
                      ),
                      Image.file(
                        File(_lastPhotoPath!),
                        height: 280,
                        fit: BoxFit.cover,
                      ),
                      Padding(
                        padding: const EdgeInsets.all(12.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Caminho: $_lastPhotoPath',
                              style: const TextStyle(fontSize: 11, color: Colors.grey),
                            ),
                            if (_galleryUri != null) ...[
                              const SizedBox(height: 4),
                              Text(
                                'Galeria: $_galleryUri',
                                style: const TextStyle(fontSize: 11, color: Colors.grey),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStatusChip() {
    Color bg;
    Color fg;
    String label;

    switch (_connectionState) {
      case 'BOUND':
        bg = Colors.green.shade100;
        fg = Colors.green.shade800;
        label = 'Conectado';
        break;
      case 'CONNECTING':
        bg = Colors.orange.shade100;
        fg = Colors.orange.shade800;
        label = 'Conectando...';
        break;
      case 'PHOTO':
        bg = Colors.purple.shade100;
        fg = Colors.purple.shade800;
        label = 'Baixando Foto...';
        break;
      case 'ERROR':
        bg = Colors.red.shade100;
        fg = Colors.red.shade800;
        label = 'Erro';
        break;
      default:
        bg = Colors.grey.shade200;
        fg = Colors.grey.shade700;
        label = 'Desconectado';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        label,
        style: TextStyle(color: fg, fontWeight: FontWeight.bold, fontSize: 12),
      ),
    );
  }
}
