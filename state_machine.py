"""
Optional LangGraph-based state machine for collections agent.

This module provides a structured state machine for managing conversation flow.
To use it, install langgraph: pip install langgraph langchain-core

Usage:
    from state_machine import CollectionsStateMachine
    
    state_machine = CollectionsStateMachine()
    next_state = await state_machine.process(user_message, current_state)
"""

from typing import Dict, Any, Optional, TypedDict
import logging

logger = logging.getLogger(__name__)

try:
    from langgraph.graph import StateGraph, END
    from langchain_core.messages import HumanMessage, AIMessage
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.warning("LangGraph not available. Install with: pip install langgraph langchain-core")


class ConversationState(TypedDict):
    """State structure for the collections conversation."""
    # Facts extracted from conversation
    customer_name: Optional[str]
    overdue_amount: Optional[str]
    due_date: Optional[str]
    ptp_date: Optional[str]
    reference_number: Optional[str]
    language_preference: Optional[str]
    
    # Confirmation states
    identity_confirmed: bool
    awareness_confirmed: bool
    payment_made: Optional[bool]  # None = not asked, True = yes, False = no
    
    # Current state
    current_step: str  # "greeting", "confirm_identity", "confirm_awareness", "capture_action", "closing"
    
    # Conversation history
    messages: list
    
    # Metadata
    session_id: str
    turn_count: int


class CollectionsStateMachine:
    """State machine for collections agent conversation flow."""
    
    def __init__(self):
        if not LANGGRAPH_AVAILABLE:
            raise ImportError("LangGraph not available. Install with: pip install langgraph langchain-core")
        
        self.graph = self._build_graph()
        self.compiled = self.graph.compile()
    
    def _build_graph(self) -> StateGraph:
        """Build the state machine graph."""
        workflow = StateGraph(ConversationState)
        
        # Define nodes
        workflow.add_node("greeting", self._greeting_node)
        workflow.add_node("confirm_identity", self._confirm_identity_node)
        workflow.add_node("confirm_awareness", self._confirm_awareness_node)
        workflow.add_node("capture_action", self._capture_action_node)
        workflow.add_node("closing", self._closing_node)
        
        # Define edges
        workflow.set_entry_point("greeting")
        workflow.add_edge("greeting", "confirm_identity")
        workflow.add_conditional_edges(
            "confirm_identity",
            self._should_skip_identity,
            {
                "skip": "confirm_awareness",
                "ask": "confirm_identity",
            }
        )
        workflow.add_conditional_edges(
            "confirm_awareness",
            self._should_skip_awareness,
            {
                "skip": "capture_action",
                "ask": "confirm_awareness",
            }
        )
        workflow.add_conditional_edges(
            "capture_action",
            self._is_action_captured,
            {
                "done": "closing",
                "continue": "capture_action",
            }
        )
        workflow.add_edge("closing", END)
        
        return workflow
    
    async def _greeting_node(self, state: ConversationState) -> ConversationState:
        """Initial greeting node."""
        state["current_step"] = "greeting"
        state["turn_count"] = state.get("turn_count", 0) + 1
        return state
    
    async def _confirm_identity_node(self, state: ConversationState) -> ConversationState:
        """Confirm customer identity."""
        state["current_step"] = "confirm_identity"
        state["turn_count"] = state.get("turn_count", 0) + 1
        return state
    
    async def _confirm_awareness_node(self, state: ConversationState) -> ConversationState:
        """Confirm awareness of overdue payment."""
        state["current_step"] = "confirm_awareness"
        state["turn_count"] = state.get("turn_count", 0) + 1
        return state
    
    async def _capture_action_node(self, state: ConversationState) -> ConversationState:
        """Capture payment action (payment made, PTP date, or callback)."""
        state["current_step"] = "capture_action"
        state["turn_count"] = state.get("turn_count", 0) + 1
        return state
    
    async def _closing_node(self, state: ConversationState) -> ConversationState:
        """Closing node."""
        state["current_step"] = "closing"
        return state
    
    def _should_skip_identity(self, state: ConversationState) -> str:
        """Determine if identity confirmation should be skipped."""
        if state.get("identity_confirmed", False):
            return "skip"
        return "ask"
    
    def _should_skip_awareness(self, state: ConversationState) -> str:
        """Determine if awareness confirmation should be skipped."""
        if state.get("awareness_confirmed", False):
            return "skip"
        return "ask"
    
    def _is_action_captured(self, state: ConversationState) -> str:
        """Check if action has been captured."""
        payment_made = state.get("payment_made")
        ptp_date = state.get("ptp_date")
        reference_number = state.get("reference_number")
        
        # Action is captured if:
        # - Payment made + reference number
        # - Payment not made + PTP date
        if payment_made is True and reference_number:
            return "done"
        if payment_made is False and ptp_date:
            return "done"
        if payment_made is None:
            return "continue"  # Still need to ask
        return "continue"  # Partial info, need more
    
    async def process(self, user_message: str, current_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process a user message and return next state."""
        if current_state is None:
            current_state = {
                "customer_name": None,
                "overdue_amount": None,
                "due_date": None,
                "ptp_date": None,
                "reference_number": None,
                "language_preference": None,
                "identity_confirmed": False,
                "awareness_confirmed": False,
                "payment_made": None,
                "current_step": "greeting",
                "messages": [],
                "session_id": "",
                "turn_count": 0,
            }
        
        # Convert to ConversationState
        state = ConversationState(**current_state)
        
        # Add user message
        state["messages"].append(HumanMessage(content=user_message))
        
        # Run the state machine
        try:
            result = await self.compiled.ainvoke(state)
            return dict(result)
        except Exception as exc:
            logger.error("State machine error: %s", exc)
            return dict(state)


# Fallback simple state machine (no LangGraph dependency)
class SimpleStateMachine:
    """Simple state machine without LangGraph dependency."""
    
    STEPS = [
        "greeting",
        "confirm_identity",
        "confirm_awareness",
        "capture_action",
        "closing",
    ]
    
    def __init__(self):
        self.current_step_index = 0
    
    def get_current_step(self) -> str:
        """Get current step name."""
        if self.current_step_index < len(self.STEPS):
            return self.STEPS[self.current_step_index]
        return "closing"
    
    def advance_step(self, state: Dict[str, Any]) -> str:
        """Advance to next step based on state."""
        current = self.get_current_step()
        
        if current == "confirm_identity" and state.get("identity_confirmed", False):
            self.current_step_index += 1
        elif current == "confirm_awareness" and state.get("awareness_confirmed", False):
            self.current_step_index += 1
        elif current == "capture_action":
            payment_made = state.get("payment_made")
            ptp_date = state.get("ptp_date")
            reference_number = state.get("reference_number")
            
            if payment_made is True and reference_number:
                self.current_step_index += 1
            elif payment_made is False and ptp_date:
                self.current_step_index += 1
        
        return self.get_current_step()
    
    def should_ask_question(self, state: Dict[str, Any]) -> bool:
        """Determine if we should ask the current step's question."""
        current = self.get_current_step()
        
        if current == "confirm_identity":
            return not state.get("identity_confirmed", False)
        elif current == "confirm_awareness":
            return not state.get("awareness_confirmed", False)
        elif current == "capture_action":
            payment_made = state.get("payment_made")
            if payment_made is None:
                return True
            if payment_made is True:
                return not bool(state.get("reference_number"))
            if payment_made is False:
                return not bool(state.get("ptp_date"))
        
        return False
