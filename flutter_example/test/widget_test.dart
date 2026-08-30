import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_example/main.dart';

void main() {
  testWidgets('Renders XK Glasses Example App', (WidgetTester tester) async {
    await tester.pumpWidget(const XkGlassesExampleApp());
    expect(find.text('XK One Pro · Mini App'), findsOneWidget);
    expect(find.text('Conexão Bluetooth SPP'), findsOneWidget);
    expect(find.text('Capturar Imagem'), findsOneWidget);
  });
}
