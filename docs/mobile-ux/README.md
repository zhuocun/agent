# Mobile UX

Mobile-UX audit-and-spec track (ST1–ST5). Four read-only audits (ST1–ST4) feed
one executable spec (ST5), which is the single source of truth for the
downstream implementation buckets.

## Documents

- [ST1-type-audit.md](./ST1-type-audit.md) — mobile type-size audit.
- [ST2-touch-audit.md](./ST2-touch-audit.md) — tap-target audit (iOS HIG 44×44pt).
- [ST3-input-audit.md](./ST3-input-audit.md) — input-zoom & keyboard-scroll audit.
- [ST4-native-gap-audit.md](./ST4-native-gap-audit.md) — native-feel gap audit (PWA).
- [ST5-spec.md](./ST5-spec.md) — Phase B spec synthesizing ST1–ST4 into buckets ST-6/7/8/9. **Start here.**

## Reading order

ST5 resolves overlaps across the four audits and partitions every fix into the
ST-6/7/8/9 implementation buckets. Read [ST5-spec.md](./ST5-spec.md) first; drop
into [ST1](./ST1-type-audit.md), [ST3](./ST3-input-audit.md), or
[ST4](./ST4-native-gap-audit.md) for the source rationale behind a given bucket
([ST2](./ST2-touch-audit.md) backs the touch-target bucket).

## Related canon

- [Docs index](../README.md)
- [UX best practices — mobile](../ux-best-practices/mobile-ux.md)
- [PRD 03 — Mobile & Cross-Platform](../prd/03-mobile-cross-platform.md)
