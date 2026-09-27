from unittest.mock import AsyncMock, patch

import pytest

from app.services.simulation import SimulationController, SimulationError


def test_start_replay_uses_six_am_and_ignores_a_second_click():
    controller = SimulationController()
    process = type("Proc", (), {"poll": lambda self: None})()
    with patch("app.services.simulation._dataset_paths", return_value=("schedule.csv", "traffic.csv")), \
         patch("app.services.simulation.subprocess.Popen", return_value=process) as popen, \
         patch("app.services.simulation.settings") as settings, \
         patch.object(controller, "stop_replay"):
        settings.replay_speed = 30
        settings.replay_start_at = "2026-01-06T06:00:00"
        assert controller.start_replay() is True
        assert controller.start_replay() is False
    command = popen.call_args.args[0]
    assert popen.call_count == 1
    assert command[command.index("--start-at") + 1] == "2026-01-06T06:00:00"
    assert "--pause-at-end" in command


def test_missing_dataset_is_reported():
    controller = SimulationController()
    with patch.object(controller, "stop_replay"), \
         patch("app.services.simulation._dataset_paths", side_effect=SimulationError("нет csv")):
        with pytest.raises(SimulationError, match="нет csv"):
            controller.start_replay()


@pytest.mark.asyncio
async def test_stop_emulator_sends_empty_units():
    controller = SimulationController()
    with patch("app.services.simulation._emulator_config", return_value={"targetHost": "host.docker.internal", "targetPort": 9201, "units": [{"unitId": 1}]}), \
         patch("app.services.simulation._emulator_request", new_callable=AsyncMock) as request:
        await controller.stop_emulator()
    request.assert_awaited_once_with(
        "POST",
        {"targetHost": "host.docker.internal", "targetPort": 9201, "units": []},
    )
