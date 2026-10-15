import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import UUID


def normalized_date(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def reconcile(db_path, *, deployment_id, canonical_name, aliases, site_code,
              started_at, ended_at, apply=False):
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise ValueError("No existe la base indicada")
    deployment_id = str(UUID(deployment_id))
    start, end = normalized_date(started_at), normalized_date(ended_at)
    if end <= start or not canonical_name:
        raise ValueError("Nombre o intervalo no valido")
    backup = None
    with sqlite3.connect(str(db_path), timeout=10) as db:
        db.execute("PRAGMA foreign_keys=ON")
        if apply:
            backup = db_path.with_name(db_path.stem + ".before-reconcile-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".db")
            with sqlite3.connect(backup) as snapshot:
                db.backup(snapshot)
            backup.chmod(0o600)
        db.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        try:
            row = db.execute(
                "SELECT d.id,d.device_id,v.name,s.code,d.started_at,d.ended_at "
                "FROM deployments d JOIN devices v ON v.id=d.device_id "
                "JOIN sites s ON s.id=d.site_id WHERE d.public_id=?", (deployment_id,),
            ).fetchone()
            if row is None or row[2] not in {canonical_name, *aliases} or row[3] != site_code:
                raise ValueError("El despliegue no coincide con el nodo y sitio autorizados")
            deployment_pk, old_device = row[:2]
            for table in ("detections", "audio_metrics"):
                bounds = db.execute(f'SELECT MIN(timestamp),MAX(timestamp) FROM "{table}" WHERE deployment_id=?',
                                    (deployment_pk,)).fetchone()
                if bounds[0] and (normalized_date(bounds[0]) < start or normalized_date(bounds[1]) > end):
                    raise ValueError("El intervalo excluiria observaciones existentes")
            canonical = db.execute("SELECT id FROM devices WHERE name=?", (canonical_name,)).fetchone()
            canonical_id = canonical[0] if canonical else old_device
            references = []
            if canonical_id != old_device:
                if db.execute("SELECT COUNT(*) FROM deployments WHERE device_id=? AND id!=?",
                              (old_device, deployment_pk)).fetchone()[0]:
                    raise ValueError("El alias tiene otros despliegues; requiere revision individual")
                for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                    quoted = table.replace('"', '""')
                    for fk in db.execute(f'PRAGMA foreign_key_list("{quoted}")').fetchall():
                        if fk[2] == "devices" and fk[4] == "id":
                            references.append((table, fk[3]))
            report = {"deployment_id": deployment_id, "previous_name": row[2], "canonical_name": canonical_name,
                      "started_at": start.isoformat(), "ended_at": end.isoformat(), "merge_device": canonical_id != old_device}
            if not apply:
                db.rollback()
                return report
            db.execute("UPDATE deployments SET started_at=?,ended_at=?,updated_at=? WHERE id=?",
                       (start.isoformat(" "), end.isoformat(" "), datetime.now(timezone.utc).isoformat(), deployment_pk))
            if canonical is None:
                db.execute("UPDATE devices SET name=? WHERE id=?", (canonical_name, old_device))
            elif canonical_id != old_device:
                for table, column in references:
                    quoted_table, quoted_column = table.replace('"', '""'), column.replace('"', '""')
                    db.execute(f'UPDATE "{quoted_table}" SET "{quoted_column}"=? WHERE "{quoted_column}"=?',
                               (canonical_id, old_device))
                db.execute("DELETE FROM devices WHERE id=?", (old_device,))
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("La reconciliacion no supera la comprobacion de integridad")
            db.commit()
            report["backup"] = str(backup)
            return report
        except Exception:
            db.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description="Reconcilia un despliegue legacy verificado entre replicas")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--canonical-name", required=True)
    parser.add_argument("--alias", action="append", default=[])
    parser.add_argument("--site-code", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--ended-at", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(reconcile(args.db, deployment_id=args.deployment_id, canonical_name=args.canonical_name,
                               aliases=args.alias, site_code=args.site_code, started_at=args.started_at,
                               ended_at=args.ended_at, apply=args.apply), indent=2))


if __name__ == "__main__":
    main()
