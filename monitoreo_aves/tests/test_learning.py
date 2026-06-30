from datetime import datetime, timezone

def _create_detection(client, species, index, confidence=0.71, amplitude=0.12):
    response = client.post(
        "/detections/",
        json={
            "species": species,
            "confidence": confidence,
            "timestamp": datetime(2026, 6, 1, 8, index, 0, tzinfo=timezone.utc).isoformat(),
            "filename": f"learning_{species.replace(' ', '_')}_{index}.wav",
            "device_name": "raspberry-learning-test",
            "amplitude": amplitude,
        },
    )
    assert response.status_code == 200
    return response.json()

def test_revisiones_consistentes_generan_sugerencia_aprendida(client):
    species = "Learning False Robin"

    for index in range(3):
        detection = _create_detection(
            client,
            species,
            index,
            confidence=0.70 + (index * 0.01),
            amplitude=0.12,
        )
        review_response = client.patch(
            f"/detections/{detection['id']}/review",
            json={
                "status": "noise",
                "reviewer": "pytest",
                "note": "Ruido recurrente validado por humano",
            },
        )
        assert review_response.status_code == 200

    rules_response = client.get("/learning/rules", params={"active_only": True})
    assert rules_response.status_code == 200

    matching_rules = [
        rule
        for rule in rules_response.json()
        if rule["original_species"] == species and rule["learned_status"] == "noise"
    ]
    assert len(matching_rules) == 1
    assert matching_rules[0]["support_count"] == 3
    assert matching_rules[0]["active"] is True

    new_detection = _create_detection(client, species, 20, confidence=0.71, amplitude=0.12)

    assert new_detection["review"] is None
    assert new_detection["learned_suggestion"] is not None
    assert new_detection["learned_suggestion"]["status"] == "noise"
    assert new_detection["learned_suggestion"]["effective_species"] == "Noise_Ruido Ambiente"
    assert new_detection["learned_suggestion"]["support_count"] == 3

def test_actualizar_misma_revision_no_duplica_soporte(client):
    species = "Learning Duplicate Warbler"
    detection = _create_detection(client, species, 40, confidence=0.66, amplitude=0.08)

    for _ in range(2):
        review_response = client.patch(
            f"/detections/{detection['id']}/review",
            json={
                "status": "corrected",
                "corrected_species": "Corrected Learning Warbler",
                "reviewer": "pytest",
            },
        )
        assert review_response.status_code == 200

    rules_response = client.get("/learning/rules")
    assert rules_response.status_code == 200

    matching_rules = [
        rule
        for rule in rules_response.json()
        if rule["original_species"] == species
        and rule["learned_status"] == "corrected"
        and rule["corrected_species"] == "Corrected Learning Warbler"
    ]
    assert len(matching_rules) == 1
    assert matching_rules[0]["support_count"] == 1
    assert matching_rules[0]["active"] is False