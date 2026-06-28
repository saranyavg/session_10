"""Unit tests for the Computer-Use Agent (CUA) skill.

Verifies the 5-layer architecture against the 3 tasks under the specified constraints:
1. Calculator Task (Deterministic Hotkeys - Layer 2a) -> Zero vision calls
2. Notepad Task (AX-tree-driven / Vision Fallback - Layer 2b / Layer 5) -> Forces vision
3. VS Code Task (Electron CDP - Layer 2c) -> Uses Electron page path
"""
import os
import json
import pytest
from pathlib import Path
from cua_skill import ComputerSkill
from schemas import NodeSpec

@pytest.mark.asyncio
async def test_calculator_task_hotkey():
    """Calculator task using deterministic hotkeys. Must complete with zero vision calls."""
    artifacts_root = Path(__file__).parent.parent / "state" / "sessions" / "test_calc"
    skill = ComputerSkill(artifacts_root=str(artifacts_root), session="test_calc_sess")
    
    # Force mock client for deterministic test runs
    skill.cua.use_mock = True
    
    node = NodeSpec(
        skill="computer",
        inputs=[],
        metadata={
            "goal": "Compute 123 * 456",
            "app": "Calculator",
            "task_type": "hotkey"
        }
    )
    
    result = await skill.run(node)
    assert result.success
    assert result.output["turns"] > 0
    assert result.output["path"] == "hotkey"
    
    # Check trajectory file
    traj_path = Path(result.output["trajectory_path"])
    assert traj_path.exists()
    
    # Read steps from trajectory
    with open(traj_path, "r", encoding="utf-8") as f:
        steps = [json.loads(line) for line in f]
        
    assert len(steps) > 0
    # Ensure no vision layer was used
    for s in steps:
        assert s["layer_used"] != "vision"

@pytest.mark.asyncio
async def test_notepad_task_vision():
    """Notepad task using AX tree and forcing vision fallback."""
    artifacts_root = Path(__file__).parent.parent / "state" / "sessions" / "test_notepad"
    skill = ComputerSkill(artifacts_root=str(artifacts_root), session="test_notepad_sess")
    
    skill.cua.use_mock = True
    
    node = NodeSpec(
        skill="computer",
        inputs=[],
        metadata={
            "goal": "Click save and type Hello",
            "app": "Notepad",
            "task_type": "vision" # forces vision fallback
        }
    )
    
    result = await skill.run(node)
    assert result.success
    assert result.output["turns"] > 0
    assert result.output["path"] == "vision"
    
    # Check trajectory file
    traj_path = Path(result.output["trajectory_path"])
    assert traj_path.exists()
    
    with open(traj_path, "r", encoding="utf-8") as f:
        steps = [json.loads(line) for line in f]
    assert any(s["layer_used"] == "vision" for s in steps)

@pytest.mark.asyncio
async def test_vscode_task_electron():
    """VS Code task using Electron CDP path."""
    artifacts_root = Path(__file__).parent.parent / "state" / "sessions" / "test_vscode"
    skill = ComputerSkill(artifacts_root=str(artifacts_root), session="test_vscode_sess")
    
    skill.cua.use_mock = True
    
    node = NodeSpec(
        skill="computer",
        inputs=[],
        metadata={
            "goal": "Evaluate console log expression",
            "app": "Visual Studio Code",
            "task_type": "electron"
        }
    )
    
    result = await skill.run(node)
    assert result.success
    assert result.output["turns"] > 0
    assert result.output["path"] == "electron"
    
    # Check trajectory file
    traj_path = Path(result.output["trajectory_path"])
    assert traj_path.exists()
    
    with open(traj_path, "r", encoding="utf-8") as f:
        steps = [json.loads(line) for line in f]
    assert any(s["action_type"] == "cdp" or s["layer_used"] == "electron" for s in steps)
