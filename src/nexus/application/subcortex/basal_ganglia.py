"""
BasalGangliaUseCase - reinforcement-learning action selection.

The basal ganglia arbitrate between competing cortical columns. Each column
submits a bid; the winner's action is executed. A Q-learning update reinforces
the chosen column's policy based on the reward the action produced.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict

from nexus.domain.ports.cognition import ActionPolicyStore, CorticalColumnRegistry
from nexus.domain.ports.event_bus import Event, EventBus, EventTopic, EventPriority


@dataclass
class ActionSelection:
    action_id: str
    column: str
    bid: float
    reward_signal: float = 0.0


@dataclass
class BiddingResult:
    selected: ActionSelection
    all_bids: Dict[str, float] = field(default_factory=dict)


class BasalGangliaUseCase:
    """Competitive bidding among cortical hexagons to pick the next action."""

    EXPLORATION_RATE = 0.1
    LEARNING_RATE = 0.2
    DISCOUNT = 0.9

    def __init__(
        self,
        column_registry: CorticalColumnRegistry,
        policy_store: ActionPolicyStore,
        event_bus: EventBus,
    ) -> None:
        self._columns = column_registry
        self._policy = policy_store
        self._event_bus = event_bus

    async def select(self, state_key: str, actions: Dict[str, str], urgency: float = 0.0) -> BiddingResult:
        """
        Each candidate column bids: bid = gated_weight * (1 + urgency) + Q-value.
        The highest bidder wins, with occasional epsilon-greedy exploration.
        """
        columns = await self._columns.list_all()
        candidates = [c for c in columns if c.name in actions]
        if not candidates:
            candidates = columns

        bids: Dict[str, float] = {}
        q_values = await self._policy.get_state(state_key)
        for column in candidates:
            action_id = actions.get(column.name, column.id)
            q = q_values.get(action_id, 0.0)
            bids[column.name] = column.bid(urgency) + q

        winner_name = max(bids, key=bids.get)
        if random.random() < self.EXPLORATION_RATE:
            winner_name = random.choice(list(bids.keys()))

        winner = next(c for c in candidates if c.name == winner_name)
        action_id = actions.get(winner.name, winner.id)
        selection = ActionSelection(action_id=action_id, column=winner.name, bid=bids[winner.name])

        await self._event_bus.publish(
            Event(
                topic=EventTopic.ACTION_SELECTED,
                payload={"state": state_key, "action": action_id, "column": winner.name, "bid": bids[winner.name]},
                priority=EventPriority.NORMAL,
            )
        )
        return BiddingResult(selected=selection, all_bids=bids)

    async def apply_reward(self, state_key: str, action_id: str, reward: float) -> None:
        """Q-learning update: Q(s,a) += alpha * (reward - Q(s,a))."""
        old = await self._policy.get_value(state_key, action_id)
        updated = old + self.LEARNING_RATE * (reward - old)
        await self._policy.set_value(state_key, action_id, updated)

    async def update_from_event(self, event: Event) -> None:
        """Wire a cortex outcome event back into the policy as a reward."""
        payload = event.payload
        state_key = payload.get("state", "default")
        action_id = payload.get("action") or payload.get("tool_id")
        reward = float(payload.get("reward", payload.get("success", 0.0)))
        if action_id is not None:
            await self.apply_reward(state_key, action_id, reward)
