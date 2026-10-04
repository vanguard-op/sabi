// Generates the AI service's copy of the Sabi A2UI catalog from the single
// authored Dart document (FEAT-011, C-012 revision 2).
//
// The catalog is authored once in `sabi_catalog_document.dart`; the AI service
// ships a JSON artifact (A2UI: the catalog is a deploy-time artifact known to
// both sides, never fetched at runtime). This generator materialises that
// artifact from the one source, and `--check` fails when the committed file and
// the Dart document disagree — the drift guard that runs in CI.
//
// Run from `apps/mobile`:
//   dart run lib/a2ui/generate_catalog.dart --check   # CI: fail on divergence
//   dart run lib/a2ui/generate_catalog.dart --write   # rewrite the artifact
//
// It imports only the Flutter-free document library, so plain `dart run` works.

import 'dart:convert';
import 'dart:io';

import 'sabi_catalog_document.dart';

/// The generated artifact, relative to the repository root.
const String _outputPath =
    'services/ai/core/catalogs/sabi_a2ui_v1.json';

const JsonEncoder _encoder = JsonEncoder.withIndent('  ');

/// Walks up from the current directory to the repository root (the directory
/// holding both `apps/` and `services/`), so the command runs from anywhere.
Directory _repoRoot() {
  var dir = Directory.current.absolute;
  while (true) {
    if (Directory('${dir.path}/apps').existsSync() &&
        Directory('${dir.path}/services').existsSync()) {
      return dir;
    }
    final parent = dir.parent;
    if (parent.path == dir.path) {
      stderr.writeln('error: repository root not found from ${Directory.current.path}');
      exit(2);
    }
    dir = parent;
  }
}

/// Parses JSON so two encodings of the same data compare equal regardless of
/// key order or whitespace.
Object? _decode(String text) => jsonDecode(text);

bool _deepEquals(Object? a, Object? b) {
  if (a is Map && b is Map) {
    if (a.length != b.length) return false;
    for (final key in a.keys) {
      if (!b.containsKey(key)) return false;
      if (!_deepEquals(a[key], b[key])) return false;
    }
    return true;
  }
  if (a is List && b is List) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (!_deepEquals(a[i], b[i])) return false;
    }
    return true;
  }
  return a == b;
}

void main(List<String> args) {
  const known = {'--check', '--write'};
  final unknown = args.where((a) => !known.contains(a));
  if (unknown.isNotEmpty || args.length > 1) {
    stderr.writeln(
      'usage: dart run lib/a2ui/generate_catalog.dart [--check|--write]',
    );
    exit(2);
  }

  final write = args.contains('--write');
  final file = File('${_repoRoot().path}/$_outputPath');
  final generated = buildSabiCatalogDocument();
  final generatedJson = '${_encoder.convert(generated)}\n';

  if (write) {
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(generatedJson);
    stdout.writeln('wrote $_outputPath from sabi_catalog_document.dart');
    return;
  }

  if (!file.existsSync()) {
    stderr.writeln('error: $_outputPath is missing; run with --write');
    exit(1);
  }
  final committed = _decode(file.readAsStringSync());
  if (!_deepEquals(committed, generated)) {
    stderr.writeln(
      'error: $_outputPath has drifted from sabi_catalog_document.dart.\n'
      'The catalog is authored once in Dart; regenerate the artifact with:\n'
      '  cd apps/mobile && dart run lib/a2ui/generate_catalog.dart --write',
    );
    exit(1);
  }
  stdout.writeln('ok: $_outputPath matches sabi_catalog_document.dart');
}
