import 'package:flutter/material.dart';

const appPanelBorder = Color(0xFFDDE3D8);
const appPanelMuted = Color(0xFFF9FAF6);
const appGreenSoft = Color(0xFFE4EEE5);
const appBlueSoft = Color(0xFFE4EFF0);
const appWarmSoft = Color(0xFFF2EBDD);
const appTextMuted = Color(0xFF5F6F65);

class BirdMonitorLogo extends StatelessWidget {
  final double size;
  final Color? birdColor;
  final Color? accentColor;

  const BirdMonitorLogo({
    super.key,
    this.size = 28,
    this.birdColor,
    this.accentColor,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: size,
      child: ClipOval(
        child: Image.asset(
          'assets/birdmonitor-ostrero.png',
          fit: BoxFit.cover,
          filterQuality: FilterQuality.high,
        ),
      ),
    );
  }
}

class AppPage extends StatelessWidget {
  final List<Widget> children;
  final EdgeInsetsGeometry padding;
  final double maxWidth;

  const AppPage({
    super.key,
    required this.children,
    this.padding = const EdgeInsets.all(16),
    this.maxWidth = 980,
  });

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: padding,
      children: [
        Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxWidth),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: children,
            ),
          ),
        ),
      ],
    );
  }
}

class AppSecondaryScaffold extends StatelessWidget {
  final String title;
  final Widget child;
  final List<Widget>? actions;

  const AppSecondaryScaffold({
    super.key,
    required this.title,
    required this.child,
    this.actions,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        centerTitle: true,
        leading: IconButton(
          tooltip: 'Volver',
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.maybePop(context),
        ),
        title: Text(title),
        actions: actions,
      ),
      body: child,
    );
  }
}

class AppHeaderPanel extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final Widget? trailing;
  final Widget? leading;

  const AppHeaderPanel({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    this.trailing,
    this.leading,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primaryContainer,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child:
                    leading ??
                    Icon(
                      icon,
                      color: Theme.of(context).colorScheme.primary,
                      size: 28,
                    ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 4),
                  Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            if (trailing != null) ...[const SizedBox(width: 12), trailing!],
          ],
        ),
      ),
    );
  }
}

class AppSectionTitle extends StatelessWidget {
  final String title;
  final String? subtitle;

  const AppSectionTitle({super.key, required this.title, this.subtitle});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(2, 18, 2, 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleLarge),
                if (subtitle != null) ...[
                  const SizedBox(height: 2),
                  Text(subtitle!, style: Theme.of(context).textTheme.bodySmall),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class AppMetricGrid extends StatelessWidget {
  final List<Widget> children;

  const AppMetricGrid({super.key, required this.children});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final columns = width >= 900
            ? 4
            : width >= 680
            ? 3
            : width >= 520
            ? 2
            : 1;
        final gap = 10.0;
        final itemWidth = (width - (columns - 1) * gap) / columns;

        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: [
            for (final child in children)
              SizedBox(width: itemWidth, child: child),
          ],
        );
      },
    );
  }
}

class AppMetricCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final String? detail;

  const AppMetricCard({
    super.key,
    required this.icon,
    required this.label,
    required this.value,
    this.detail,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  icon,
                  color: Theme.of(context).colorScheme.primary,
                  size: 20,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              value,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(
                context,
              ).textTheme.titleMedium?.copyWith(fontSize: 18),
            ),
            if (detail != null) ...[
              const SizedBox(height: 4),
              Text(
                detail!,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class AppDataPanel extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;

  const AppDataPanel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(0),
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(padding: padding, child: child),
    );
  }
}

class AppFieldHero extends StatelessWidget {
  final IconData icon;
  final String eyebrow;
  final String title;
  final String subtitle;
  final Widget? status;
  final Widget? child;

  const AppFieldHero({
    super.key,
    required this.icon,
    required this.eyebrow,
    required this.title,
    required this.subtitle,
    this.status,
    this.child,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Card(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [colorScheme.primaryContainer, Colors.white],
          ),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  DecoratedBox(
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.72),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: appPanelBorder),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(10),
                      child: Icon(icon, color: colorScheme.primary, size: 24),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          eyebrow,
                          style: Theme.of(context).textTheme.bodySmall
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(
                            context,
                          ).textTheme.titleLarge?.copyWith(fontSize: 18),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          subtitle,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  if (status != null) ...[const SizedBox(width: 12), status!],
                ],
              ),
              if (child != null) ...[const SizedBox(height: 10), child!],
            ],
          ),
        ),
      ),
    );
  }
}

class AppSoundBars extends StatelessWidget {
  final bool active;
  final double height;
  final Color? color;

  const AppSoundBars({
    super.key,
    this.active = false,
    this.height = 44,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final effectiveColor = color ?? Theme.of(context).colorScheme.primary;
    final bars = active
        ? const [0.28, 0.62, 0.42, 0.86, 0.55, 1.0, 0.48, 0.72, 0.36]
        : const [0.18, 0.26, 0.2, 0.32, 0.22, 0.28, 0.2, 0.24, 0.18];

    return SizedBox(
      height: height,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          for (final bar in bars) ...[
            Expanded(
              child: Align(
                alignment: Alignment.center,
                child: FractionallySizedBox(
                  heightFactor: bar,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: active
                          ? effectiveColor
                          : Color.lerp(effectiveColor, Colors.white, 0.62),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: const SizedBox(width: 5),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 5),
          ],
        ],
      ),
    );
  }
}

class AppDetailRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const AppDetailRow({
    super.key,
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: Theme.of(context).colorScheme.primary),
        const SizedBox(width: 8),
        Expanded(
          child: Text(label, style: Theme.of(context).textTheme.bodySmall),
        ),
        const SizedBox(width: 12),
        Expanded(
          flex: 2,
          child: Text(
            value,
            textAlign: TextAlign.end,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
      ],
    );
  }
}

class AppQuickAction extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const AppQuickAction({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return AppDataPanel(
      padding: EdgeInsets.zero,
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: appGreenSoft,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Icon(
                    icon,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }
}

class AppStatusPill extends StatelessWidget {
  final String text;
  final IconData icon;
  final Color? color;

  const AppStatusPill({
    super.key,
    required this.text,
    required this.icon,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final effectiveColor = color ?? Theme.of(context).colorScheme.primary;
    final backgroundColor = Color.lerp(effectiveColor, Colors.white, 0.86);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: backgroundColor,
        border: Border.all(
          color: Color.lerp(effectiveColor, Colors.white, 0.58)!,
        ),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: effectiveColor),
            const SizedBox(width: 6),
            Text(
              text,
              style: TextStyle(
                color: effectiveColor,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }
}