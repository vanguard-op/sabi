import 'package:flutter/material.dart';

import '../design_system/tokens.dart';

/// A labelled text input on the shared input tokens. Every field has a visible
/// label and an error slot, so it meets the accessibility rules for labelled
/// inputs and colour independence (error is text, not just a red border).
class SabTextField extends StatelessWidget {
  const SabTextField({
    super.key,
    required this.label,
    this.controller,
    this.hint,
    this.errorText,
    this.helperText,
    this.obscureText = false,
    this.enabled = true,
    this.maxLines = 1,
    this.keyboardType,
    this.textInputAction,
    this.autofocus = false,
    this.onSubmitted,
    this.suffixIcon,
  });

  final String label;
  final TextEditingController? controller;
  final String? hint;
  final String? errorText;
  final String? helperText;
  final bool obscureText;
  final bool enabled;
  final int maxLines;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final bool autofocus;
  final ValueChanged<String>? onSubmitted;
  final Widget? suffixIcon;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      enabled: enabled,
      obscureText: obscureText,
      maxLines: obscureText ? 1 : maxLines,
      keyboardType: keyboardType,
      textInputAction: textInputAction,
      autofocus: autofocus,
      onSubmitted: onSubmitted,
      style: SabTypography.body.copyWith(
        color: SabColorTokens.of(context).textPrimary,
      ),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        errorText: errorText,
        helperText: helperText,
        suffixIcon: suffixIcon,
      ),
    );
  }
}
