import 'package:flutter/material.dart';

import '../design_system/tokens.dart';

/// A single loading placeholder block. Movement is a gentle opacity pulse that
/// stops under the OS reduce-motion setting, and the block is hidden from
/// assistive tech in favour of a live-region busy announcement.
class SabSkeleton extends StatefulWidget {
  const SabSkeleton({
    super.key,
    this.width = double.infinity,
    this.height = SabSpacing.md,
    this.radius = SabRadii.sm,
  });

  final double width;
  final double height;
  final double radius;

  @override
  State<SabSkeleton> createState() => _SabSkeletonState();
}

class _SabSkeletonState extends State<SabSkeleton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: SabMotion.skeletonPulse,
  );

  @override
  void initState() {
    super.initState();
    _controller.repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = SabColorTokens.of(context);
    final bar = Container(
      width: widget.width,
      height: widget.height,
      decoration: BoxDecoration(
        color: colors.grey200,
        borderRadius: BorderRadius.circular(widget.radius),
      ),
    );
    if (MediaQuery.disableAnimationsOf(context)) {
      return ExcludeSemantics(child: bar);
    }
    return ExcludeSemantics(
      child: FadeTransition(
        opacity: Tween<double>(begin: 0.45, end: 1).animate(
          CurvedAnimation(parent: _controller, curve: SabMotion.standard),
        ),
        child: bar,
      ),
    );
  }
}

/// A receipt-shaped skeleton used for first-load of Home and Receipts.
class SabSkeletonList extends StatelessWidget {
  const SabSkeletonList({super.key, this.rows = 4});

  final int rows;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Loading',
      liveRegion: true,
      child: ListView(
        padding: EdgeInsets.zero,
        children: [
          for (var i = 0; i < rows; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: SabSpacing.md),
              child: Container(
                padding: const EdgeInsets.all(SabSpacing.md),
                decoration: BoxDecoration(
                  color: SabColorTokens.of(context).surface,
                  borderRadius: BorderRadius.circular(SabRadii.md),
                  border: Border.all(color: SabColorTokens.of(context).border),
                ),
                child: const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SabSkeleton(width: 160, height: SabSpacing.md),
                    SizedBox(height: SabSpacing.sm),
                    SabSkeleton(width: 100, height: SabSpacing.sm),
                    SizedBox(height: SabSpacing.md),
                    SabSkeleton(height: SabSizes.iconLg),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
