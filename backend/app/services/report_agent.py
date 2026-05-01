"""
Report Agent Service
Generates simulation reports using local graph memory with ReACT pattern

Features:
1. Generate reports based on simulation requirements and local graph information
2. Plan report structure first, then generate section by section
3. Each section uses ReACT multi-round reasoning and reflection
4. Support user conversations with autonomous retrieval tool calls
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .local_graph_store import tokenize_text
from .graph_tools import (
    GraphToolsService,
    SearchResult,
    InsightForgeResult,
    PanoramaResult,
    InterviewResult
)

logger = get_logger('univerra.report_agent')


class ReportLogger:
    """
    Report Agent Detailed Logger

    Generates agent_log.jsonl file in the report folder, recording each step in detail.
    Each line is a complete JSON object containing timestamp, action type, detailed content, etc.
    """

    def __init__(self, report_id: str):
        """
        Initialize logger

        Args:
            report_id: Report ID, used to determine log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Ensure log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)

    def _get_elapsed_time(self) -> float:
        """Get elapsed time from start (seconds)"""
        return (datetime.now() - self.start_time).total_seconds()

    def log(
        self,
        action: str,
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Record a log entry

        Args:
            action: action type, e.g. 'start', 'tool_call', 'llm_response', 'section_complete', etc.
            stage: current stage, e.g. 'planning', 'generating', 'completed'
            details: details dictionary, not truncated
            section_title: current section title (optional)
            section_index: current section index (optional)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }

        # Append to JSONL file
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Record report generation start"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Report generation task started"
            }
        )

    def log_planning_start(self):
        """Record outline planning start"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Starting report outline planning"}
        )

    def log_planning_context(self, context: Dict[str, Any]):
        """Record context information obtained during planning"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Fetching simulation context information",
                "context": context
            }
        )

    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Record outline planning completion"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Outline planning complete",
                "outline": outline_dict
            }
        )

    def log_section_start(self, section_title: str, section_index: int):
        """Record section generation start"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Starting section generation: {section_title}"}
        )

    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Record ReACT reasoning process"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT round {iteration} of reasoning"
            }
        )

    def log_tool_call(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Record tool call"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Calling tool: {tool_name}"
            }
        )

    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Record tool call result (full content, not truncated)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Full result, not truncated
                "result_length": len(result),
                "message": f"Tool {tool_name} returned result"
            }
        )

    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Record LLM response (full content, not truncated)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Full response, not truncated
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM response (tool call: {has_tool_calls}, final answer: {has_final_answer})"
            }
        )

    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Record section content generation (content only, does not represent full section completion)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Full content, not truncated
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Section {section_title} content generation complete"
            }
        )

    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Record section generation complete

        Frontend should listen to this log to determine if a section is truly complete and get full content
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Section {section_title} generation complete"
            }
        )

    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Record report generation complete"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Report generation complete"
            }
        )

    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Record error"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"Error occurred: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report Agent Console Logger

    Writes console-style logs (INFO, WARNING, etc.) to console_log.txt in the report folder.
    These logs differ from agent_log.jsonl, being plain text console output.
    """

    def __init__(self, report_id: str):
        """
        Initialize console logger

        Args:
            report_id: Report ID, used to determine log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()

    def _ensure_log_file(self):
        """Ensure log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)

    def _setup_file_handler(self):
        """Set up file handler to write logs to file simultaneously"""
        import logging

        # Create file handler
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)

        # Use the same concise format as console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)

        # Add to report_agent related loggers
        loggers_to_attach = [
            'univerra.report_agent',
            'univerra.graph_tools',
        ]

        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Avoid duplicate addition
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)

    def close(self):
        """Close file handler and remove from loggers"""
        import logging

        if self._file_handler:
            loggers_to_detach = [
                'univerra.report_agent',
                'univerra.graph_tools',
            ]

            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)

            self._file_handler.close()
            self._file_handler = None

    def __del__(self):
        """Ensure file handler is closed on destruction"""
        self.close()


class ReportStatus(str, Enum):
    """Report status"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Report section"""
    title: str
    content: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "description": self.description,
        }

    def to_markdown(self, level: int = 2) -> str:
        """Convert to Markdown format"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Report outline"""
    title: str
    summary: str
    sections: List[ReportSection]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }

    def to_markdown(self) -> str:
        """Convert to Markdown format"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Complete report"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Prompt Template Constants
# ═══════════════════════════════════════════════════════════════

# ── Tool Descriptions ──

TOOL_DESC_INSIGHT_FORGE = """\
[Deep Insight Retrieval - Powerful Retrieval Tool]
This is our powerful retrieval function, designed for deep analysis. It will:
1. Automatically decompose your question into multiple sub-questions
2. Retrieve information from the simulation graph across multiple dimensions
3. Integrate results from semantic search, entity analysis, relationship chain tracking, and fresh web research when available
4. Return the most comprehensive and in-depth retrieval content

[Use Cases]
- Need to deeply analyze a topic
- Need to understand multiple aspects of an event
- Need to gather rich material to support report sections

[Return Content]
- Related fact texts (can be directly quoted)
- Core entity insights
- Relationship chain analysis
- Fresh source-backed market or world signals when available"""

TOOL_DESC_PANORAMA_SEARCH = """\
[Panorama Search - Full Picture View]
This tool provides a complete overview of simulation results, especially suitable for understanding event evolution. It will:
1. Retrieve all related nodes and relationships
2. Distinguish between currently valid facts and historical/expired facts
3. Help you understand how public sentiment evolved

[Use Cases]
- Need to understand the complete development trajectory of events
- Need to compare sentiment changes across different stages
- Need to get comprehensive entity and relationship information

[Return Content]
- Currently valid facts (latest simulation results)
- Historical/expired facts (evolution records)
- All involved entities"""

TOOL_DESC_QUICK_SEARCH = """\
[Quick Search - Fast Retrieval]
Lightweight fast retrieval tool, suitable for simple, direct information queries.

[Use Cases]
- Need to quickly find specific information
- Need to verify a fact
- Simple information retrieval

[Return Content]
- List of facts most relevant to the query"""

TOOL_DESC_INTERVIEW_AGENTS = """\
[Deep Interview - Real Agent Interview (Dual Platform)]
Calls the OASIS simulation environment interview API to conduct real interviews with running simulation Agents!
This is not LLM simulation, but real interview API calls to get original answers from simulation Agents.
Interviews on both Twitter and Reddit platforms simultaneously by default for more comprehensive perspectives.

Feature workflow:
1. Automatically reads persona files to understand all simulation Agents
2. Intelligently selects Agents most relevant to the interview topic (e.g., students, media, officials)
3. Automatically generates interview questions
4. Calls /api/simulation/interview/batch API for real interviews on both platforms
5. Integrates all interview results for multi-perspective analysis

[Use Cases]
- Need to understand perspectives from different roles (How do students see it? Media? Officials?)
- Need to collect multiple opinions and positions
- Need to get real answers from simulation Agents (from OASIS simulation environment)
- Want to make the report more vivid with "interview transcripts"

[Return Content]
- Identity information of interviewed Agents
- Interview responses from each Agent on both Twitter and Reddit platforms
- Key quotes (can be directly cited)
- Interview summary and opinion comparison

[Important] The OASIS simulation environment must be running to use this feature!"""

# ── Outline Planning Prompt ──

PLAN_SYSTEM_PROMPT = """\
You are an expert in writing "Future Prediction Reports," with a "God's-eye view" of the simulated world — you can observe every Agent's behavior, statements, and interactions within the simulation.

[Core Concept]
We have built a simulated world and injected specific "simulation requirements" as variables. The evolution results of the simulated world represent predictions of what may happen in the future. What you are observing is not "experimental data," but a "rehearsal of the future."

[Your Task]
Write a "Future Prediction Report" that answers:
1. Under the conditions we set, what happened in the future?
2. How did various Agents (population groups) react and act?
3. What noteworthy future trends and risks does this simulation reveal?

[Report Positioning]
- This is a simulation-based future prediction report, revealing "if this happens, what will the future look like"
- Focus on prediction results: event trajectories, group reactions, emergent phenomena, potential risks
- Agent behaviors and statements in the simulated world are predictions of future population behavior
- This is NOT an analysis of the current real-world situation
- This is NOT a generic public opinion summary
- Every time-based claim must be anchored to the configured simulation horizon, phase window, or observed simulated timestamp when available
- Distinguish observed simulation evidence from forecast interpretation and uncertainty
- Use the configured outcome probability table when discussing probabilities; do not invent new percentages
- Include counterfactual sensitivity when the evidence supports multiple plausible futures

[Section Count Limits]
- Minimum 2 sections, maximum 5 sections
- No subsections needed; each section should contain complete content
- Content should be concise, focused on core prediction findings
- Section structure should be designed based on prediction results at your discretion
- Section titles must be specific to the scenario and evidence; avoid generic placeholders that could fit any topic
- At least one section should clearly state where the evidence is strong vs. weak
- The final section must be a short "Small Summary" that closes the full report with the bottom line, time horizon, confidence, and biggest risk
- At least one non-summary section should cover outcome probabilities, evidence strength, and counterfactual sensitivity

Please output a JSON-formatted report outline in the following format:
{
    "title": "Report title",
    "summary": "Report summary (one sentence summarizing the core prediction findings)",
    "sections": [
        {
            "title": "Section title",
            "description": "Section content description"
        }
    ]
}

Note: The sections array must contain at least 2 and at most 5 elements!"""

PLAN_USER_PROMPT_TEMPLATE = """\
[Prediction Scenario Setup]
Variable injected into the simulated world (simulation requirement): {simulation_requirement}

[Simulation Time Horizon and Accuracy Calibration]
{temporal_context}

[Simulated World Scale]
- Number of entities in the simulation: {total_nodes}
- Number of relationships between entities: {total_edges}
- Entity type distribution: {entity_types}
- Number of active Agents: {total_entities}

[Sample of Future Facts Predicted by the Simulation]
{related_facts_json}

Please review this future rehearsal from a "God's-eye view":
1. Under the conditions we set, what state does the future present?
2. How did various population groups (Agents) react and act?
3. What noteworthy future trends does this simulation reveal?

Based on the prediction results, design the most appropriate report section structure.

[Reminder] Report section count: minimum 2, maximum 5. The last section must be "Small Summary". Content should be concise and focused on core prediction findings."""

# ── Section Generation Prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert in writing "Future Prediction Reports," currently writing one section of the report.

Report title: {report_title}
Report summary: {report_summary}
Prediction scenario (simulation requirement): {simulation_requirement}

Current section to write: {section_title}

═══════════════════════════════════════════════════════════════
[Core Concept]
═══════════════════════════════════════════════════════════════

The simulated world is a rehearsal of the future. We injected specific conditions (simulation requirements) into the simulated world. The behaviors and interactions of Agents in the simulation are predictions of future population behavior.

Your task is to:
- Reveal what happened in the future under the set conditions
- Predict how various population groups (Agents) reacted and acted
- Discover noteworthy future trends, risks, and opportunities

Do NOT write this as an analysis of the current real-world situation.
DO focus on "what will the future look like" — simulation results ARE the predicted future.

═══════════════════════════════════════════════════════════════
[Most Important Rules - Must Follow]
═══════════════════════════════════════════════════════════════

1. [Must Call Tools to Observe the Simulated World]
   - You are observing a future rehearsal from a "God's-eye view"
   - All content must come from events and Agent behaviors in the simulated world
   - Do NOT use your own knowledge to write report content
   - Each section should usually call at least 1 tool (maximum 5) to observe the simulated world representing the future

2. [Must Quote Agents' Original Behaviors and Statements]
   - Agent statements and behaviors are predictions of future population behavior
   - Use quotation format in the report to display these predictions, e.g.:
     > "A certain group would say: original content..."
   - These quotations are the core evidence of simulation predictions

3. [Language Consistency - Quoted Content Must Match Report Language]
   - Tool-returned content may contain mixed languages
   - When quoting tool-returned content, translate it into fluent language matching the report
   - Maintain the original meaning while ensuring natural expression
   - This rule applies to both body text and quotation blocks (> format)

4. [Faithfully Present Prediction Results]
   - Report content must reflect simulation results representing the future
   - Do not add information that does not exist in the simulation
   - If information is insufficient in certain areas, state this honestly
   - Never pad the section with generic advice, broad business common sense, or placeholder commentary
   - Never write speculative filler such as "might say", "could note", "broader context suggests", "future updates may provide", or "technical challenges prevented access" unless the tool result explicitly says that and no better evidence exists
   - Only include quotation blocks when you have concrete retrieved text to quote or closely translate
   - Anchor timelines to the simulation phase windows and simulated timestamps when available
   - Say "confidence is limited" when the evidence bundle, tool observations, or calibration profile is weak

═══════════════════════════════════════════════════════════════
[Format Specifications - Extremely Important!]
═══════════════════════════════════════════════════════════════

[One Section = Minimum Content Unit]
- Each section is the minimum unit of the report
- Do NOT use any Markdown headings (#, ##, ###, #### etc.) within a section
- Do NOT add the section title at the beginning of the content
- Section titles are added automatically by the system; you only need to write body text
- Use **bold**, paragraph breaks, quotations, and lists to organize content, but do not use headings

[Correct Example]
```
This section analyzes the public opinion dynamics of the event. Through in-depth analysis of simulation data, we found...

**Initial Outbreak Phase**

Weibo, as the first scene of public opinion, served as the primary information source:

> "Weibo contributed 68% of the initial volume..."

**Emotion Amplification Phase**

Short-video platforms further amplified the event's impact:

- Strong visual impact
- High emotional resonance
```

[Incorrect Example]
```
## Executive Summary        <- Wrong! Do not add any headings
### 1. Initial Phase        <- Wrong! Do not use ### for subsections
#### 1.1 Detailed Analysis  <- Wrong! Do not use #### for details

This section analyzes...
```

═══════════════════════════════════════════════════════════════
[Available Retrieval Tools] (Call 1-5 times per section)
═══════════════════════════════════════════════════════════════

{tools_description}

[Tool Usage Suggestions - Mix different tools, do not use only one type]
- insight_forge: Deep insight analysis, automatically decomposes questions and retrieves facts and relationships across multiple dimensions
- panorama_search: Wide-angle panoramic search, understand the full picture of events, timelines, and evolution
- quick_search: Quickly verify a specific information point
- interview_agents: Interview simulation Agents, get first-person perspectives and real reactions from different roles

═══════════════════════════════════════════════════════════════
[Workflow]
═══════════════════════════════════════════════════════════════

Each response can only do ONE of the following two things (not both simultaneously):

Option A - Call a tool:
Output your thinking, then call a tool using this format:
<tool_call>
{{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
</tool_call>
The system will execute the tool and return results to you. You must not write tool results yourself.

Option B - Output final content:
When you have gathered sufficient information through tools, output section content starting with "Final Answer:".

Strictly prohibited:
- Do NOT include both a tool call and Final Answer in the same response
- Do NOT fabricate tool results (Observations); all tool results are injected by the system
- Each response may call at most one tool

═══════════════════════════════════════════════════════════════
[Section Content Requirements]
═══════════════════════════════════════════════════════════════

1. Content must be based on simulation data retrieved through tools
2. Extensively quote original text to demonstrate simulation results
3. Use Markdown formatting (but no headings):
   - Use **bold text** to highlight key points (instead of subheadings)
   - Use lists (- or 1.2.3.) to organize key points
   - Use blank lines to separate paragraphs
   - Do NOT use #, ##, ###, #### or any heading syntax
4. [Quotation Format - Must Be Standalone Paragraphs]
   Quotations must be standalone paragraphs with a blank line before and after:

   Correct format:
   ```
   The school's response was considered lacking in substance.

   > "The school's response pattern appeared rigid and slow in the fast-changing social media environment."

   This assessment reflects widespread public dissatisfaction.
   ```

   Incorrect format:
   ```
   The school's response was considered lacking in substance. > "The school's response pattern..." This assessment reflects...
   ```
5. Maintain logical coherence with other sections
6. [Avoid Repetition] Carefully read the already completed section content below; do not repeat the same information
7. [Emphasis] Do not add any headings! Use **bold** instead of subheadings
8. [Specificity Test] Each completed section should contain at least 2 concrete evidence anchors chosen from: named entities, quoted facts, numerical counts, or explicit relationship chains
9. [Evidence Scoring] For each major conclusion, add a brief evidence-strength phrase such as "Evidence strength: high/medium/low" based on retrieved support"""

SECTION_USER_PROMPT_TEMPLATE = """\
Already completed section content (please read carefully to avoid repetition):
{previous_content}

═══════════════════════════════════════════════════════════════
[Current Task] Write section: {section_title}
═══════════════════════════════════════════════════════════════

[Important Reminders]
1. Carefully read the already completed sections above to avoid repeating the same content!
2. You must call tools to obtain simulation data before starting
3. Mix different tools; do not use only one type
4. Report content must come from retrieval results; do not use your own knowledge
5. If the retrieved evidence is weak, be specific about what is missing instead of writing generic filler
6. Do not use phrases like "might say", "could note", or "broader context suggests"
7. Use the preloaded evidence bundle first; then call tools only to fill the most important remaining gaps
8. Prefer concrete evidence over coverage breadth: it is better to write a narrower but well-supported section than a broad generic one
9. If this section is "Small Summary", keep it to 4-6 bullets or short paragraphs and include: bottom line, time horizon, confidence, main driver, and main risk

[Format Warning - Must Follow]
- Do NOT write any headings (#, ##, ###, #### are all prohibited)
- Do NOT write "{section_title}" as the opening
- Section titles are added automatically by the system
- Write body text directly; use **bold** instead of subheadings

Please begin:
1. First think (Thought) about what information this section needs
2. Then call tools (Action) to obtain simulation data
3. After gathering sufficient information, output Final Answer (body text only, no headings)"""

SECTION_DIRECT_WRITE_SYSTEM_PROMPT_TEMPLATE = """\
You are writing one section of a future prediction report from evidence that has already been gathered for you.

Report title: {report_title}
Report summary: {report_summary}
Prediction scenario: {simulation_requirement}
Current section: {section_title}

Rules:
- Do not call tools, functions, actions, or agents
- Do not output JSON, XML, markdown headings, or <tool_call> blocks
- Do not output the prefix "Final Answer:"
- Use only the supplied evidence and clearly state limits where evidence is weak
- Prefer concrete entities, quoted facts, counts, and relationship chains over generic advice
- Do not invent percentages, probability splits, timelines, permissions, offers, or stakeholder actions unless they appear in the supplied evidence
- If the scenario lacks personal details, explicitly say which details are missing instead of silently assuming them
- Use **bold**, bullet lists, and quote blocks when helpful, but no headings
- Anchor time claims to the supplied forecast horizon or simulated timestamps
- If writing "Small Summary", keep it concise: 4-6 bullets or short paragraphs only
- For major conclusions, include evidence strength: high, medium, or low
"""

SECTION_DIRECT_WRITE_USER_PROMPT_TEMPLATE = """\
Completed sections so far:
{previous_content}

Preloaded grounding brief:
{grounding_brief}

Evidence bundle:
{evidence_brief}

Retrieved tool observations:
{tool_observations}

Write the body text for section "{section_title}" only.
Do not repeat earlier sections.
Do not invent missing evidence.
If evidence is thin, say exactly what is missing in this section instead of filling space with general commentary.
Do not invent numeric splits, made-up percentages, or personal details that the user never stated.
"""

# ── ReACT Loop Message Templates ──

REACT_OBSERVATION_TEMPLATE = """\
Observation (Retrieval results):

═══ Tool {tool_name} returned ═══
{result}

═══════════════════════════════════════════════════════════════
Tools called: {tool_calls_count}/{max_tool_calls} times (used: {used_tools_str}){unused_hint}
- If information is sufficient: output section content starting with "Final Answer:" (must quote the above original text)
- If more information is needed: call a tool to continue retrieval
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "[Notice] You have only called {tool_calls_count} tools, minimum required is {min_tool_calls} times. "
    "Please call more tools to gather additional simulation data before outputting Final Answer. {unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Currently only called {tool_calls_count} tools, minimum required is {min_tool_calls} times. "
    "Please call tools to obtain simulation data. {unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Tool call count has reached the limit ({tool_calls_count}/{max_tool_calls}), no more tool calls allowed. "
    'Please immediately output section content starting with "Final Answer:" based on the obtained information.'
)

REACT_UNUSED_TOOLS_HINT = "\nYou have not yet used: {unused_list}. Consider trying different tools for multi-angle information."

REACT_FORCE_FINAL_MSG = "Tool call limit reached. Please output Final Answer: directly and generate section content."

# ── Chat Prompt ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
You are a concise and efficient simulation prediction assistant.

[Background]
Prediction scenario: {simulation_requirement}

[Simulation Time Horizon and Accuracy Calibration]
{temporal_context}

[Generated Analysis Report]
{report_content}

[Rules]
1. Prioritize answering questions based on the report content above
2. Answer questions directly; avoid lengthy deliberation
3. Only call tools for additional data retrieval when the report content is insufficient
4. Answers should be concise, clear, and well-reasoned

[Available Tools] (Use only when needed, maximum 1-2 calls)
{tools_description}

[Tool Call Format]
<tool_call>
{{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
</tool_call>

[Answer Style]
- Concise and direct; do not write lengthy responses
- Use > format to quote key content
- Provide conclusions first, then explain reasoning
- End with a short "Small summary:" line or bullet list"""

CHAT_OBSERVATION_SUFFIX = "\n\nPlease answer the question concisely."


# ═══════════════════════════════════════════════════════════════
# ReportAgent Main Class
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - Simulation Report Generation Agent

    Uses ReACT (Reasoning + Acting) pattern:
    1. Planning phase: Analyze simulation requirements, plan report outline structure
    2. Generation phase: Generate content section by section, each section can call tools multiple times
    3. Reflection phase: Check content completeness and accuracy
    """

    # Maximum tool calls per section
    MAX_TOOL_CALLS_PER_SECTION = 5

    # Maximum reflection rounds
    MAX_REFLECTION_ROUNDS = 3

    # Maximum tool calls per chat
    MAX_TOOL_CALLS_PER_CHAT = 2
    GENERIC_FAILURE_PATTERNS = (
        "technical challenges",
        "technical limitations",
        "future updates may provide",
        "broader context suggests",
        "might say",
        "could note",
        "cannot provide detailed",
        "unable to provide detailed",
    )
    OUTLINE_GENERIC_TITLES = {
        "introduction",
        "overview",
        "analysis",
        "technology as a key enabler",
        "community validation and support",
        "potential risks and gaps in knowledge",
        "cross-disciplinary aspirations and challenges",
    }

    def __init__(
        self,
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        graph_tools: Optional[GraphToolsService] = None
    ):
        """
        Initialize Report Agent

        Args:
            graph_id: Graph ID
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description
            llm_client: LLM client (optional)
            graph_tools: graph tools service (optional)
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement

        self.llm = llm_client or LLMClient()
        self.graph_tools = graph_tools or GraphToolsService()
        self._simulation_config_cache: Optional[Dict[str, Any]] = None

        # Tool definitions
        self.tools = self._define_tools()

        # Logger (initialized in generate_report)
        self.report_logger: Optional[ReportLogger] = None
        # Console logger (initialized in generate_report)
        self.console_logger: Optional[ReportConsoleLogger] = None

        logger.info(f"ReportAgent initialized: graph_id={graph_id}, simulation_id={simulation_id}")

    def _load_simulation_config(self) -> Dict[str, Any]:
        if self._simulation_config_cache is not None:
            return self._simulation_config_cache

        config_path = os.path.join(
            Config.OASIS_SIMULATION_DATA_DIR,
            self.simulation_id,
            "simulation_config.json",
        )
        if not os.path.exists(config_path):
            self._simulation_config_cache = {}
            return self._simulation_config_cache

        try:
            with open(config_path, "r", encoding="utf-8") as file:
                self._simulation_config_cache = json.load(file)
        except Exception as error:
            logger.warning(f"Failed to load simulation config for report context: {error}")
            self._simulation_config_cache = {}

        return self._simulation_config_cache

    def _build_temporal_report_context(self) -> str:
        config = self._load_simulation_config()
        if not config:
            return "No simulation_config.json was available; time claims must be treated as lower-confidence."

        temporal = config.get("temporal_forecast_config") or {}
        calibration = config.get("calibration_profile") or {}
        environment = config.get("environment_context") or {}
        time_config = config.get("time_config") or {}
        ensemble = config.get("ensemble_config") or {}
        dashboard = config.get("calibration_dashboard") or {}
        outcome_rows = config.get("outcome_probability_table") or []
        counterfactuals = config.get("counterfactual_controls") or []
        signal_plan = config.get("real_world_signal_plan") or {}

        lines = [
            f"- Region/timezone: {environment.get('primary_region', 'Unknown')} / {temporal.get('timezone') or environment.get('timezone', 'UTC')}",
            f"- Forecast start: {temporal.get('forecast_start_at', 'not specified')}",
            f"- Forecast end: {temporal.get('forecast_end_at', 'not specified')}",
            f"- Horizon label: {temporal.get('horizon_label', 'not specified')}",
            f"- Simulated duration: {time_config.get('total_simulation_hours', 'unknown')} hours at {time_config.get('minutes_per_round', 'unknown')} minutes/round",
            f"- Accuracy mode: {calibration.get('recommended_mode', 'balanced')}; confidence: {calibration.get('confidence_label', 'moderate')} ({calibration.get('confidence_score', 'n/a')})",
            f"- Recommended ensemble runs: {ensemble.get('recommended_runs', 'not specified')}",
            f"- Quality dashboard: overall {dashboard.get('overall_quality_score', 'n/a')}, real-world prediction {dashboard.get('real_world_prediction_score', 'n/a')}",
        ]

        uncertainty_factors = calibration.get("uncertainty_factors") or []
        if uncertainty_factors:
            lines.append("- Uncertainty factors: " + "; ".join(str(item) for item in uncertainty_factors[:5]))

        phase_windows = temporal.get("phase_windows") or []
        if phase_windows:
            lines.append("- Phase windows:")
            for phase in phase_windows[:5]:
                lines.append(
                    "  - {name}: hour {start_hour}-{end_hour}, {start_at} to {end_at}; {expected_focus}".format(
                        name=phase.get("name", "phase"),
                        start_hour=phase.get("start_hour", "?"),
                        end_hour=phase.get("end_hour", "?"),
                        start_at=phase.get("start_at", "?"),
                        end_at=phase.get("end_at", "?"),
                        expected_focus=phase.get("expected_focus", ""),
                    )
                )

        scenarios = temporal.get("future_scenarios") or []
        if scenarios:
            lines.append("- Scenario variants to consider:")
            for scenario in scenarios[:3]:
                lines.append(
                    f"  - {scenario.get('name', 'scenario')} ({scenario.get('relative_likelihood', 'conditional')}): "
                    f"{scenario.get('expected_outcome', '')}"
                )

        if outcome_rows:
            lines.append("- Outcome probability table:")
            for row in outcome_rows[:5]:
                lines.append(
                    f"  - {row.get('outcome', 'Outcome')}: {row.get('probability_percent', '?')}% "
                    f"({row.get('confidence', 'confidence not specified')}); {row.get('why', '')}"
                )

        if counterfactuals:
            lines.append("- Counterfactual controls:")
            for control in counterfactuals[:6]:
                lines.append(f"  - {control.get('label', control.get('id', 'control'))}: {control.get('expected_effect', '')}")

        signal_sources = signal_plan.get("sources") or []
        if signal_sources:
            lines.append("- Real-world signal plan:")
            for source in signal_sources[:5]:
                lines.append(f"  - {source.get('name', 'source')} ({source.get('status', '')}): {source.get('use', '')}")

        return "\n".join(lines)

    def _summary_section(self) -> ReportSection:
        return ReportSection(
            title="Small Summary",
            description=(
                "End the full report with 4-6 concise bullets covering bottom line, time horizon, "
                "confidence, main driver, and biggest risk or evidence gap."
            ),
        )

    def _ensure_final_summary_section(self, outline: ReportOutline) -> ReportOutline:
        summary_titles = {"small summary", "summary", "executive summary", "final summary"}
        existing_summary = None
        other_sections = []

        for section in outline.sections:
            if section.title.strip().lower() in summary_titles and existing_summary is None:
                existing_summary = section
            else:
                other_sections.append(section)

        summary_section = existing_summary or self._summary_section()
        summary_section.title = "Small Summary"
        if not summary_section.description:
            summary_section.description = self._summary_section().description

        max_non_summary = 4
        outline.sections = other_sections[:max_non_summary] + [summary_section]
        if len(outline.sections) < 2:
            outline.sections.insert(
                0,
                ReportSection(
                    title="What the Simulation Predicts",
                    description="Summarize the strongest predicted future outcome from simulation evidence.",
                ),
            )
        return outline

    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Define available tools"""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "The question or topic you want to deeply analyze",
                    "report_context": "Context of the current report section (optional, helps generate more precise sub-questions)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Search query, used for relevance ranking",
                    "include_expired": "Whether to include expired/historical content (default True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Search query string",
                    "limit": "Number of results to return (optional, default 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Interview topic or requirement description (e.g., 'understand students views on the dormitory formaldehyde incident')",
                    "max_agents": "Maximum number of Agents to interview (optional, default 5, max 10)"
                }
            }
        }

    def _build_section_grounding_brief(self, section_title: str) -> str:
        context = self.graph_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=f"{self.simulation_requirement}\nSection focus: {section_title}",
            limit=12,
        )
        stats = context.get("graph_statistics", {})
        facts = context.get("related_facts", [])[:8]
        entities = context.get("entities", [])[:8]

        lines = [
            "[Initial Grounding Context]",
            "[Simulation Time Horizon and Accuracy Calibration]",
            self._build_temporal_report_context(),
            "",
            f"- Graph nodes: {stats.get('total_nodes', 0)}",
            f"- Graph edges: {stats.get('total_edges', 0)}",
            f"- Evidence hits for this section: {context.get('supporting_evidence_count', len(facts))}",
            "- Top retrieved facts:",
        ]

        if facts:
            lines.extend([f"  - {fact}" for fact in facts])
        else:
            lines.append("  - No direct facts retrieved yet")

        lines.append("- Relevant entities:")
        if entities:
            lines.extend([f"  - {entity.get('name', '')} ({entity.get('type', '')}): {entity.get('summary', '')}" for entity in entities])
        else:
            lines.append("  - No clearly matched entities yet")

        web_research = context.get("web_research") or {}
        web_answer = (web_research.get("answer") or "").strip()
        if web_answer:
            lines.append("- Fresh web research:")
            lines.append(f"  - {web_answer}")

        reddit_research = context.get("reddit_research") or {}
        reddit_summary = (reddit_research.get("summary") or "").strip()
        if reddit_summary:
            lines.append("- Fresh Reddit discussion signals:")
            lines.append(f"  - {reddit_summary}")

        scenario_context = self._extract_scenario_context()
        if scenario_context["stated_facts"]:
            lines.append("- Directly stated personal context:")
            lines.extend([f"  - {item}" for item in scenario_context["stated_facts"][:5]])
        if scenario_context["missing_context"]:
            lines.append("- Missing context that must not be silently assumed:")
            lines.extend([f"  - {item}" for item in scenario_context["missing_context"][:5]])

        return "\n".join(lines)

    def _looks_overly_generic(self, text: str) -> bool:
        lowered = (text or "").lower()
        return any(pattern in lowered for pattern in self.GENERIC_FAILURE_PATTERNS)

    def _build_section_evidence_bundle(self, section: ReportSection) -> Dict[str, Any]:
        focus_parts = [section.title, section.description, self.simulation_requirement]
        focus_query = " ".join(part.strip() for part in focus_parts if part and part.strip())
        return self.graph_tools.build_evidence_bundle(
            graph_id=self.graph_id,
            query=focus_query,
            simulation_requirement=self.simulation_requirement,
            limit=8,
        )

    def _render_evidence_bundle(self, bundle: Dict[str, Any]) -> str:
        lines = [
            "[Preloaded Evidence Bundle]",
            f"- Query focus: {bundle.get('combined_query', '')}",
            f"- Evidence strength score: {bundle.get('evidence_strength', 0)}",
            f"- Direct evidence hits: {bundle.get('supporting_evidence_count', 0)}",
            f"- Active facts in wider panorama: {bundle.get('active_count', 0)}",
            f"- Historical facts in wider panorama: {bundle.get('historical_count', 0)}",
            "- Strongest facts:",
        ]

        facts = bundle.get("top_facts", [])[:5]
        if facts:
            lines.extend([f"  - {fact}" for fact in facts])
        else:
            lines.append("  - No strong direct facts found yet")

        lines.append("- Most relevant entities:")
        entities = bundle.get("entities", [])[:5]
        if entities:
            for entity in entities:
                lines.append(
                    f"  - {entity.get('name', '')} ({entity.get('type', 'Entity')}): {entity.get('summary', '')}"
                )
        else:
            lines.append("  - No clearly matched entities")

        if bundle.get("relation_chains"):
            lines.append("- Relationship chains:")
            lines.extend([f"  - {chain}" for chain in bundle.get("relation_chains", [])[:4]])

        if bundle.get("historical_facts"):
            lines.append("- Change-over-time evidence:")
            lines.extend([f"  - {fact}" for fact in bundle.get("historical_facts", [])[:3]])

        web_research = bundle.get("web_research") or {}
        if web_research.get("answer"):
            lines.append("- Live web-backed signals:")
            lines.append(f"  - {web_research.get('answer')}")
            for source in (web_research.get("sources") or [])[:3]:
                title = source.get("title", "Source")
                domain = source.get("domain", "")
                url = source.get("url", "")
                lines.append(f"  - {title} ({domain}): {url}")

        reddit_research = bundle.get("reddit_research") or {}
        if reddit_research.get("summary"):
            lines.append("- Live Reddit discussion signals:")
            lines.append(f"  - {reddit_research.get('summary')}")
            for post in (reddit_research.get("posts") or [])[:3]:
                title = post.get("title", "Thread")
                subreddit = post.get("subreddit", "")
                permalink = post.get("permalink", "")
                lines.append(f"  - r/{subreddit}: {title} ({permalink})")

        if bundle.get("evidence_gaps"):
            lines.append("- Evidence gaps:")
            lines.extend([f"  - {gap}" for gap in bundle.get("evidence_gaps", [])])

        return "\n".join(lines)

    def _count_grounded_markers(self, text: str, bundle: Dict[str, Any]) -> int:
        lowered = (text or "").lower()
        score = 0

        if "\n>" in text or text.strip().startswith(">"):
            score += 2
        if re.search(r"\b\d+\b", text or ""):
            score += 1

        for entity in bundle.get("entities", [])[:6]:
            name = (entity.get("name") or "").strip().lower()
            if len(name) >= 4 and name in lowered:
                score += 1

        top_fact_tokens = []
        for fact in bundle.get("top_facts", [])[:4]:
            tokens = [token for token in tokenize_text(fact) if len(token) >= 5]
            top_fact_tokens.extend(tokens[:3])
        for token in dict.fromkeys(top_fact_tokens):
            if token in lowered:
                score += 1

        return score

    def _build_rewrite_with_evidence_prompt(self, bundle: Dict[str, Any]) -> str:
        lines = [
            "Your draft is still too generic or not grounded enough.",
            "Rewrite it using only the retrieved evidence below.",
            "Requirements:",
            "- Mention at least 2 concrete entities or relationship chains when available",
            "- Include at least 1 direct quote block from retrieved facts when available",
            "- If evidence is weak, explicitly state the precise gap instead of writing general advice",
            "- Do not use phrases like 'might say', 'could note', 'broader context suggests', or 'future updates may provide'",
            "- Do not invent numeric splits, percentages, offers, permissions, or personal details that are absent from the evidence",
            "",
            self._render_evidence_bundle(bundle),
        ]
        return "\n".join(lines)

    def _extract_scenario_context(self) -> Dict[str, List[str]]:
        text = (self.simulation_requirement or "").strip()
        lowered = text.lower()
        stated_facts: List[str] = []
        missing_context: List[str] = []

        time_matches = re.findall(r"\b\d+\s*(?:hours?|hrs?|minutes?|mins?|days?|weeks?|months?)\b", text, flags=re.IGNORECASE)
        if time_matches:
            stated_facts.append("Time constraints mentioned: " + ", ".join(dict.fromkeys(match.strip() for match in time_matches[:3])))
        else:
            missing_context.append("Exact time budget or deadline is not specified")

        stakeholder_keywords = [
            "teacher", "professor", "manager", "boss", "client", "parent", "partner",
            "friend", "team", "recruiter", "interviewer", "mentor",
        ]
        mentioned_stakeholders = [word for word in stakeholder_keywords if re.search(rf"\b{re.escape(word)}\b", lowered)]
        if mentioned_stakeholders:
            stated_facts.append("Stakeholders explicitly mentioned: " + ", ".join(dict.fromkeys(mentioned_stakeholders[:5])))
        else:
            missing_context.append("Other people involved are not clearly identified")

        scenario_keywords = [
            "exam", "assignment", "project", "interview", "party", "deadline",
            "career", "job", "backend", "frontend", "cybersecurity", "python",
        ]
        scenario_terms = [word for word in scenario_keywords if re.search(rf"\b{re.escape(word)}\b", lowered)]
        if scenario_terms:
            stated_facts.append("Scenario topics directly stated: " + ", ".join(dict.fromkeys(scenario_terms[:6])))
        else:
            missing_context.append("The exact subject matter or task is underspecified")

        if re.search(r"\b(extension|offer|offered|approval|approved|permission|allowed)\b", lowered):
            stated_facts.append("Support, approval, or flexibility is explicitly mentioned in the user scenario")
        else:
            missing_context.append("No explicit offer, approval, or flexibility from another person is stated")

        workload_keywords = ["work", "shift", "class", "study", "homework", "assignment", "job", "office"]
        workload_terms = [word for word in workload_keywords if re.search(rf"\b{re.escape(word)}\b", lowered)]
        if workload_terms:
            stated_facts.append("Existing obligations mentioned: " + ", ".join(dict.fromkeys(workload_terms[:5])))
        else:
            missing_context.append("Current workload or competing obligations are not described")

        return {
            "stated_facts": stated_facts,
            "missing_context": missing_context,
        }

    def _find_unsupported_claims(self, text: str, bundle: Dict[str, Any]) -> List[str]:
        content = (text or "").strip()
        if not content:
            return []

        evidence_parts = [
            self.simulation_requirement,
            bundle.get("combined_query", ""),
            " ".join(bundle.get("top_facts", [])),
            " ".join(bundle.get("historical_facts", [])),
            " ".join(bundle.get("relation_chains", [])),
        ]
        for entity in bundle.get("entities", []):
            evidence_parts.append(entity.get("name", ""))
            evidence_parts.append(entity.get("summary", ""))
        web_research = bundle.get("web_research") or {}
        evidence_parts.append(web_research.get("answer", ""))
        for source in web_research.get("sources", []) or []:
            evidence_parts.append(source.get("title", ""))
            evidence_parts.append(source.get("content", ""))
            evidence_parts.append(source.get("domain", ""))

        evidence_text = " ".join(part for part in evidence_parts if part).lower()
        lowered = content.lower()
        issues: List[str] = []

        generated_ratios = set(re.findall(r"\b\d{1,3}/\d{1,3}/\d{1,3}\b", content))
        evidence_ratios = set(re.findall(r"\b\d{1,3}/\d{1,3}/\d{1,3}\b", evidence_text))
        unsupported_ratios = sorted(generated_ratios - evidence_ratios)
        if unsupported_ratios:
            issues.append("unsupported numeric split: " + ", ".join(unsupported_ratios[:3]))

        generated_percentages = set(re.findall(r"\b\d{1,3}%\b", content))
        evidence_percentages = set(re.findall(r"\b\d{1,3}%\b", evidence_text))
        unsupported_percentages = sorted(generated_percentages - evidence_percentages)
        if unsupported_percentages:
            issues.append("unsupported percentages: " + ", ".join(unsupported_percentages[:4]))

        stakeholder_terms = ["teacher", "professor", "boss", "manager", "client", "parent", "partner", "friend"]
        unsupported_stakeholders = [
            term for term in stakeholder_terms
            if re.search(rf"\b{term}\b", lowered) and not re.search(rf"\b{term}\b", evidence_text)
        ]
        if unsupported_stakeholders:
            issues.append("unsupported stakeholder mentions: " + ", ".join(unsupported_stakeholders[:4]))

        action_terms = ["extension", "offered", "approved", "permission", "allowed", "agreed"]
        unsupported_actions = [
            term for term in action_terms
            if re.search(rf"\b{term}\b", lowered) and not re.search(rf"\b{term}\b", evidence_text)
        ]
        if unsupported_actions:
            issues.append("unsupported offers or approvals: " + ", ".join(unsupported_actions[:4]))

        return issues

    def _build_deterministic_section_fallback(
        self,
        section: ReportSection,
        bundle: Dict[str, Any],
    ) -> str:
        if section.title.strip().lower() == "small summary":
            simulation_config = self._load_simulation_config()
            temporal = simulation_config.get("temporal_forecast_config") or {}
            top_facts = bundle.get("top_facts", [])
            entities = bundle.get("entities", [])
            evidence_gaps = bundle.get("evidence_gaps", [])
            lines = [
                "- **Bottom line:** The most defensible forecast is the one directly supported by the retrieved simulation facts, not a guaranteed real-world outcome.",
                f"- **Time horizon:** {temporal.get('forecast_start_at', 'not specified')} to {temporal.get('forecast_end_at', 'not specified')} ({temporal.get('timezone', 'UTC')}).",
            ]
            if entities:
                lines.append(
                    "- **Main driver:** "
                    + ", ".join(entity.get("name", "") for entity in entities[:3] if entity.get("name"))
                    + " are the clearest actors in the evidence bundle."
                )
            if top_facts:
                lines.append(f'- **Strongest evidence:** "{top_facts[0]}"')
            if evidence_gaps:
                lines.append("- **Confidence limit:** " + "; ".join(evidence_gaps[:3]) + ".")
            else:
                lines.append("- **Confidence limit:** Treat the forecast as simulation-conditioned; it should not be read as a factual guarantee.")
            return "\n".join(lines)

        lines = []
        evidence_hits = bundle.get("supporting_evidence_count", 0)
        entities = bundle.get("entities", [])
        relation_chains = bundle.get("relation_chains", [])
        top_facts = bundle.get("top_facts", [])
        historical_facts = bundle.get("historical_facts", [])
        evidence_gaps = bundle.get("evidence_gaps", [])

        if top_facts:
            leading_entities = ", ".join(entity.get("name", "") for entity in entities[:3] if entity.get("name"))
            lead = f"The strongest simulation signal in this area comes from {evidence_hits} matched facts"
            if leading_entities:
                lead += f" centered on {leading_entities}"
            lines.append(lead + ".")
        else:
            lines.append(
                f"The simulation evidence for this theme is thin: only {evidence_hits} direct matches were retrieved for this section."
            )

        if top_facts:
            lines.append("")
            lines.append("**Direct evidence**")
            for fact in top_facts[:3]:
                lines.append("")
                lines.append(f'> "{fact}"')

        scenario_context = self._extract_scenario_context()
        if scenario_context["stated_facts"]:
            lines.append("")
            lines.append("**Directly stated context**")
            for item in scenario_context["stated_facts"][:4]:
                lines.append(f"- {item}")

        if entities:
            lines.append("")
            lines.append("**Most relevant actors**")
            for entity in entities[:4]:
                summary = (entity.get("summary") or "").strip()
                actor_line = f"- {entity.get('name', '')} ({entity.get('type', 'Entity')})"
                if summary:
                    actor_line += f": {summary}"
                lines.append(actor_line)

        if relation_chains:
            lines.append("")
            lines.append("**Observed links**")
            for chain in relation_chains[:3]:
                lines.append(f"- {chain}")

        if historical_facts:
            lines.append("")
            lines.append("**What changed over time**")
            for fact in historical_facts[:2]:
                lines.append(f"- {fact}")

        if evidence_gaps:
            lines.append("")
            lines.append(
                "The weak point in this section is "
                + ", ".join(evidence_gaps)
                + ", so conclusions beyond the facts above should be treated as low-confidence."
            )

        if scenario_context["missing_context"]:
            lines.append("")
            lines.append("**Missing personal context**")
            for item in scenario_context["missing_context"][:4]:
                lines.append(f"- {item}")

        return "\n".join(line for line in lines if line is not None).strip()

    def _should_avoid_llm_direct_tool_calls(self) -> bool:
        base_url = (getattr(self.llm, "base_url", "") or "").lower()
        model = (getattr(self.llm, "model", "") or "").lower()
        return "groq" in base_url or "gpt-oss" in model

    def _clean_generated_section_text(self, text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = re.sub(r'<tool_call>.*?</tool_call>', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r'^Final Answer:\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'^\s*```(?:markdown)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```\s*$', '', cleaned)
        return cleaned.strip()

    def _finalize_section_text(self, section: ReportSection, text: str) -> str:
        cleaned = self._clean_generated_section_text(text)
        if section.title.strip().lower() != "small summary":
            return cleaned

        lines = [line.rstrip() for line in cleaned.splitlines()]
        meaningful = [line for line in lines if line.strip()]
        if len(meaningful) <= 6 and len(cleaned) <= 1400:
            return cleaned

        selected = []
        for line in meaningful:
            if line.lstrip().startswith(("-", "*", "1.", "2.", "3.", "4.", "5.", "6.")):
                selected.append(line)
            elif not selected:
                selected.append(line)
            if len(selected) >= 6:
                break

        if not selected:
            selected = meaningful[:6]

        shortened = "\n".join(selected).strip()
        if len(shortened) > 1400:
            shortened = shortened[:1397].rstrip() + "..."
        return shortened

    def _ensure_chat_small_summary(self, response: str) -> str:
        cleaned = (response or "").strip()
        if not cleaned or "small summary" in cleaned.lower():
            return cleaned
        first_line = next((line.strip() for line in cleaned.splitlines() if line.strip()), "")
        first_line = re.sub(r"^[#>*\-\s]+", "", first_line).strip()
        if len(first_line) > 260:
            first_line = first_line[:257].rstrip() + "..."
        return f"{cleaned}\n\nSmall summary: {first_line or 'The answer is based on the generated simulation report and available evidence.'}"

    def _evaluate_report_quality(self, markdown_content: str, outline: ReportOutline) -> Dict[str, Any]:
        config = self._load_simulation_config()
        evaluator_config = config.get("evaluator_config") or {}
        expected_percentages = {
            str(row.get("probability_percent"))
            for row in config.get("outcome_probability_table", []) or []
            if row.get("probability_percent") is not None
        }
        found_percentages = set(re.findall(r"\b(\d{1,3})%", markdown_content or ""))
        unsupported_percentages = sorted(found_percentages - expected_percentages)

        checks = []
        def add_check(name: str, passed: bool, severity: str, detail: str):
            checks.append({
                "check": name,
                "passed": passed,
                "severity": severity,
                "detail": detail,
            })

        add_check(
            "small_summary_present",
            "small summary" in (markdown_content or "").lower(),
            "critical",
            "Report should end with a Small Summary section.",
        )
        add_check(
            "outcome_probability_table_used",
            not config.get("outcome_probability_table") or "probabil" in (markdown_content or "").lower(),
            "warning",
            "Report should discuss configured outcome probabilities when available.",
        )
        add_check(
            "unsupported_probability_or_percentage",
            not unsupported_percentages,
            "critical",
            "Unsupported percentages found: " + ", ".join(unsupported_percentages[:6]) if unsupported_percentages else "No unsupported percentages detected.",
        )
        add_check(
            "counterfactual_sensitivity_present",
            not config.get("counterfactual_controls") or "counterfactual" in (markdown_content or "").lower() or "sensitivity" in (markdown_content or "").lower(),
            "warning",
            "Report should include counterfactual/sensitivity discussion when controls are configured.",
        )
        add_check(
            "time_anchor_present",
            any(token in (markdown_content or "").lower() for token in ["forecast", "hour", "simulated time", "phase", "timezone"]),
            "warning",
            "Report should anchor claims to forecast time or phase windows.",
        )

        failed = [check for check in checks if not check["passed"]]
        critical_failed = [check for check in failed if check["severity"] == "critical"]
        score = max(0, 100 - len(critical_failed) * 25 - (len(failed) - len(critical_failed)) * 10)
        return {
            "enabled": bool(evaluator_config.get("enabled", True)),
            "score": score,
            "checks": checks,
            "failed_checks": failed,
            "evaluated_at": datetime.now().isoformat(),
            "summary": "Report quality checks passed." if not failed else f"{len(failed)} report quality checks need attention.",
        }

    def _collect_section_tool_observations(
        self,
        section: ReportSection,
        evidence_bundle: Dict[str, Any],
        report_context: str,
        section_index: int,
        progress_callback: Optional[Callable] = None,
    ) -> tuple[str, int]:
        focus_query = evidence_bundle.get("combined_query") or " ".join(
            part.strip()
            for part in [section.title, section.description, self.simulation_requirement]
            if part and part.strip()
        )
        tool_plan = [
            (
                "insight_forge",
                {
                    "query": focus_query,
                    "report_context": report_context,
                },
            ),
            (
                "panorama_search",
                {
                    "query": section.title,
                    "include_expired": True,
                },
            ),
            (
                "quick_search",
                {
                    "query": self.simulation_requirement,
                    "limit": 8,
                },
            ),
            (
                "interview_agents",
                {
                    "interview_topic": focus_query,
                    "max_agents": 4,
                },
            ),
        ]

        observations = []
        successful_calls = 0

        for index, (tool_name, params) in enumerate(tool_plan, start=1):
            if progress_callback:
                progress_callback(
                    "generating",
                    min(60, 12 + index * 15),
                    f"Gathering evidence with {tool_name} ({index}/{len(tool_plan)})",
                )

            if self.report_logger:
                self.report_logger.log_tool_call(
                    section_title=section.title,
                    section_index=section_index,
                    tool_name=tool_name,
                    parameters=params,
                    iteration=index,
                )

            result = self._execute_tool(tool_name, params, report_context=report_context)
            if result and "Tool execution failed:" not in result:
                successful_calls += 1

            if self.report_logger:
                self.report_logger.log_tool_result(
                    section_title=section.title,
                    section_index=section_index,
                    tool_name=tool_name,
                    result=result,
                    iteration=index,
                )

            observations.append(f"[{tool_name}]\n{result}")

        return "\n\n".join(observations), successful_calls

    def _generate_section_from_gathered_evidence(
        self,
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        grounding_brief: str,
        evidence_bundle: Dict[str, Any],
        evidence_brief: str,
        progress_callback: Optional[Callable],
        section_index: int,
    ) -> str:
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(This is the first section)"

        report_context = f"Section title: {section.title}\nSimulation requirement: {self.simulation_requirement}"
        tool_observations, tool_calls_count = self._collect_section_tool_observations(
            section=section,
            evidence_bundle=evidence_bundle,
            report_context=report_context,
            section_index=section_index,
            progress_callback=progress_callback,
        )

        messages = [
            {
                "role": "system",
                "content": SECTION_DIRECT_WRITE_SYSTEM_PROMPT_TEMPLATE.format(
                    report_title=outline.title,
                    report_summary=outline.summary,
                    simulation_requirement=self.simulation_requirement,
                    section_title=section.title,
                ),
            },
            {
                "role": "user",
                "content": SECTION_DIRECT_WRITE_USER_PROMPT_TEMPLATE.format(
                    previous_content=previous_content,
                    grounding_brief=grounding_brief,
                    evidence_brief=evidence_brief,
                    tool_observations=tool_observations,
                    section_title=section.title,
                ),
            },
        ]

        if progress_callback:
            progress_callback("generating", 72, "Drafting section from gathered evidence...")

        response = self.llm.chat(
            messages=messages,
            temperature=0.2,
            max_tokens=4096,
        )

        if self.report_logger:
            self.report_logger.log_llm_response(
                section_title=section.title,
                section_index=section_index,
                response=response or "",
                iteration=tool_calls_count + 1,
                has_tool_calls=False,
                has_final_answer="Final Answer:" in (response or ""),
            )

        final_answer = self._clean_generated_section_text(response or "")
        unsupported_claims = self._find_unsupported_claims(final_answer, evidence_bundle)

        if (
            not final_answer
            or self._looks_overly_generic(final_answer)
            or self._count_grounded_markers(final_answer, evidence_bundle) < 2
            or unsupported_claims
        ):
            final_answer = self._build_deterministic_section_fallback(section, evidence_bundle)

        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count,
            )

        return final_answer

    def _outline_needs_fallback(self, title: str, sections: List[ReportSection]) -> bool:
        if not title.strip() or len(sections) < 2:
            return True
        unique_titles = {section.title.strip().lower() for section in sections if section.title.strip()}
        if len(unique_titles) < 2:
            return True
        generic_hits = sum(1 for section in sections if section.title.strip().lower() in self.OUTLINE_GENERIC_TITLES)
        return generic_hits >= max(2, len(sections) - 1)

    def _build_fallback_outline(self, context: Dict[str, Any]) -> ReportOutline:
        entity_types = context.get("graph_statistics", {}).get("entity_types", {})
        top_entity_types = ", ".join(list(entity_types.keys())[:3]) or "key actors"
        sections = [
            ReportSection(
                title="What the Simulation Actually Shows",
                description="Summarize the clearest future-state signals directly supported by retrieved facts.",
            ),
            ReportSection(
                title="Which Actors Drive the Outcome",
                description=f"Focus on how {top_entity_types} shape the simulated outcome and which relationships matter most.",
            ),
        ]

        if context.get("related_facts"):
            sections.append(
                ReportSection(
                    title="How the Situation Evolves Over Time",
                    description="Trace the strongest sequence of changes, escalation, or stabilization visible in the evidence.",
                )
            )

        sections.append(
            ReportSection(
                title="Outcome Probabilities, Evidence, and Counterfactuals",
                description="Use the configured probability table, evidence scoring rules, and counterfactual controls to state likely paths and sensitivity.",
            )
        )

        return ReportOutline(
            title="Future Prediction Report",
            summary="An evidence-grounded summary of the simulated future, including actor behavior, trajectory, and confidence limits.",
            sections=sections[:4],
        )

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Execute tool call

        Args:
            tool_name: Tool name
            parameters: Tool parameters
            report_context: Report context (for InsightForge)

        Returns:
            Tool execution result (text format)
        """
        logger.info(f"Executing tool: {tool_name}, parameters: {parameters}")

        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.graph_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()

            elif tool_name == "panorama_search":
                # Panorama search - get full picture
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.graph_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()

            elif tool_name == "quick_search":
                # Quick search - fast retrieval
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.graph_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()

            elif tool_name == "interview_agents":
                # Deep interview - call real OASIS interview API to get simulation Agent responses (dual platform)
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.graph_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()

            # ========== Backward-compatible old tools (internally redirected to new tools) ==========

            elif tool_name == "search_graph":
                # Redirect to quick_search
                logger.info("search_graph redirected to quick_search")
                return self._execute_tool("quick_search", parameters, report_context)

            elif tool_name == "get_graph_statistics":
                result = self.graph_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.graph_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)

            elif tool_name == "get_simulation_context":
                # Redirect to insight_forge as it is more powerful
                logger.info("get_simulation_context redirected to insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)

            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.graph_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)

            else:
                return f"Unknown tool: {tool_name}. Please use one of: insight_forge, panorama_search, quick_search"

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}, error: {str(e)}")
            return f"Tool execution failed: {str(e)}"

    # Valid tool name set, used for bare JSON fallback parsing validation
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response

        Supported formats (by priority):
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. Bare JSON (entire response or single line is a tool call JSON)
        """
        tool_calls = []

        # Format 1: XML style (standard format)
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Format 2: Fallback - LLM directly outputs bare JSON (no <tool_call> tags)
        # Only attempt when Format 1 didn't match, to avoid false matches in body text
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # Response may contain thinking text + bare JSON, attempt to extract the last JSON object
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Validate whether parsed JSON is a valid tool call"""
        # Support both {"name": ..., "parameters": ...} and {"tool": ..., "params": ...} key formats
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Normalize key names to name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False

    def _get_tools_description(self) -> str:
        """Generate tool description text"""
        desc_parts = ["Available tools:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parameters: {params_desc}")
        return "\n".join(desc_parts)

    def plan_outline(
        self,
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Plan report outline

        Use LLM to analyze simulation requirements and plan report structure

        Args:
            progress_callback: Progress callback function

        Returns:
            ReportOutline: Report outline
        """
        logger.info("Starting report outline planning...")

        if progress_callback:
            progress_callback("planning", 0, "Analyzing simulation requirements...")

        # First get simulation context
        context = self.graph_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )

        if progress_callback:
            progress_callback("planning", 30, "Generating report outline...")

        system_prompt = PLAN_SYSTEM_PROMPT
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            temporal_context=self._build_temporal_report_context(),
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )

            if progress_callback:
                progress_callback("planning", 80, "Parsing outline structure...")

            # Parse outline
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content="",
                    description=section_data.get("description", ""),
                ))

            outline = ReportOutline(
                title=response.get("title", "Simulation Analysis Report"),
                summary=response.get("summary", ""),
                sections=sections
            )

            if self._outline_needs_fallback(outline.title, outline.sections):
                outline = self._build_fallback_outline(context)
            outline = self._ensure_final_summary_section(outline)

            if progress_callback:
                progress_callback("planning", 100, "Outline planning complete")

            logger.info(f"Outline planning complete: {len(outline.sections)} sections")
            return outline

        except Exception as e:
            logger.error(f"Outline planning failed: {str(e)}")
            return self._ensure_final_summary_section(self._build_fallback_outline(context))

    def _generate_section_react(
        self,
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Generate a single section's content using ReACT pattern

        ReACT loop:
        1. Thought - Analyze what information is needed
        2. Action - Call tools to obtain information
        3. Observation - Analyze tool returned results
        4. Repeat until information is sufficient or max iterations reached
        5. Final Answer - Generate section content

        Args:
            section: Section to generate
            outline: Complete outline
            previous_sections: Previous sections' content (for coherence)
            progress_callback: Progress callback
            section_index: Section index (for logging)

        Returns:
            Section content (Markdown format)
        """
        logger.info(f"ReACT generating section: {section.title}")

        # Log section start
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)

        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )

        # Build user prompt - each completed section passed in at max 4000 characters
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Each section max 4000 characters
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(This is the first section)"

        grounding_brief = self._build_section_grounding_brief(section.title)
        evidence_bundle = self._build_section_evidence_bundle(section)
        evidence_brief = self._render_evidence_bundle(evidence_bundle)

        if self._should_avoid_llm_direct_tool_calls():
            logger.info(f"Section {section.title}: using provider-safe deterministic evidence path")
            return self._generate_section_from_gathered_evidence(
                section=section,
                outline=outline,
                previous_sections=previous_sections,
                grounding_brief=grounding_brief,
                evidence_bundle=evidence_bundle,
                evidence_brief=evidence_brief,
                progress_callback=progress_callback,
                section_index=section_index,
            )

        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        ) + "\n\n" + grounding_brief + "\n\n" + evidence_brief

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # ReACT loop
        tool_calls_count = 0
        max_iterations = 5  # Maximum iteration rounds
        min_tool_calls = 1 if evidence_bundle.get("evidence_strength", 0) >= 6 else 2
        conflict_retries = 0  # Consecutive conflict count when tool call and Final Answer appear simultaneously
        used_tools = set()  # Track tools already called
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}
        successful_tool_results = 0

        # Report context, used for InsightForge sub-question generation
        report_context = f"Section title: {section.title}\nSimulation requirement: {self.simulation_requirement}"

        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating",
                    int((iteration / max_iterations) * 100),
                    f"Deep retrieval and writing ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )

            # Call LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.25,
                max_tokens=4096
            )

            # Check if LLM returned None (API exception or empty content)
            if response is None:
                logger.warning(f"Section {section.title} iteration {iteration + 1}: LLM returned None")
                # If iterations remain, add message and retry
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(empty response)"})
                    messages.append({"role": "user", "content": "Please continue generating content."})
                    continue
                # Last iteration also returned None, break to forced wrap-up
                break

            logger.debug(f"LLM response: {response[:200]}...")

            # Parse once, reuse results
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Conflict handling: LLM output both tool call and Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Section {section.title} round {iteration+1}: "
                    f"LLM output both tool call and Final Answer (conflict #{conflict_retries})"
                )

                if conflict_retries <= 2:
                    # First two times: discard response, ask LLM to re-respond
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[Format Error] Your response contains both a tool call and Final Answer, which is not allowed.\n"
                            "Each response can only do ONE of the following:\n"
                            "- Call a tool (output a <tool_call> block, do not write Final Answer)\n"
                            "- Output final content (start with 'Final Answer:', do not include <tool_call>)\n"
                            "Please re-respond, doing only one of these."
                        ),
                    })
                    continue
                else:
                    # Third time: degrade, truncate to first tool call, force execute
                    logger.warning(
                        f"Section {section.title}: {conflict_retries} consecutive conflicts, "
                        "degrading to truncated execution of first tool call"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Log LLM response
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Case 1: LLM output Final Answer ──
            if has_final_answer:
                # Tool call count insufficient, reject and require more tool calls
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(These tools have not been used yet, try them: {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Normal completion
                final_answer = response.split("Final Answer:")[-1].strip()

                if (
                    successful_tool_results > 0
                    and (
                        self._looks_overly_generic(final_answer)
                        or self._count_grounded_markers(final_answer, evidence_bundle) < 2
                    )
                    and iteration < max_iterations - 1
                ):
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": self._build_rewrite_with_evidence_prompt(evidence_bundle),
                    })
                    continue

                logger.info(f"Section {section.title} generation complete (tool calls: {tool_calls_count})")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Case 2: LLM attempted to call a tool ──
            if has_tool_calls:
                # Tool quota exhausted, explicitly inform and require Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Only execute the first tool call
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM attempted to call {len(tool_calls)} tools, only executing first: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )
                if result and "Tool execution failed:" not in result:
                    successful_tool_results += 1

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Build unused tools hint
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list=", ".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Case 3: Neither tool call nor Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Tool call count insufficient, suggest unused tools
                unused_tools = all_tools - used_tools
                unused_hint = f"(These tools have not been used yet, try them: {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # Tool calls sufficient, LLM output content without "Final Answer:" prefix
            # Accept this content directly as final answer
            logger.info(f"Section {section.title}: 'Final Answer:' prefix not detected, accepting LLM output as final content (tool calls: {tool_calls_count})")
            final_answer = response.strip()
            if (
                successful_tool_results > 0
                and (
                    self._looks_overly_generic(final_answer)
                    or self._count_grounded_markers(final_answer, evidence_bundle) < 2
                )
                and iteration < max_iterations - 1
            ):
                messages.append({"role": "user", "content": self._build_rewrite_with_evidence_prompt(evidence_bundle)})
                continue

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer

        # Reached max iterations, force generate content
        logger.warning(f"Section {section.title} reached max iterations, forcing generation")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})

        response = self.llm.chat(
            messages=messages,
            temperature=0.2,
            max_tokens=4096
        )

        # Check if LLM returned None during forced wrap-up
        if response is None:
            logger.error(f"Section {section.title} forced wrap-up: LLM returned None, using default error message")
            final_answer = "(This section generation failed: LLM returned empty response, please retry later)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response

        if self._looks_overly_generic(final_answer) or self._count_grounded_markers(final_answer, evidence_bundle) < 2:
            final_answer = self._build_deterministic_section_fallback(section, evidence_bundle)

        # Log section content generation complete
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )

        return final_answer

    def generate_report(
        self,
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Generate complete report (real-time section-by-section output)

        Each section is saved to folder immediately after completion, no need to wait for entire report.
        File structure:
        reports/{report_id}/
            meta.json       - Report metadata
            outline.json    - Report outline
            progress.json   - Generation progress
            section_01.md   - Section 1
            section_02.md   - Section 2
            ...
            full_report.md  - Complete report

        Args:
            progress_callback: Progress callback function (stage, progress, message)
            report_id: Report ID (optional, auto-generated if not provided)

        Returns:
            Report: Complete report
        """
        import uuid

        # Auto-generate report_id if not provided
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()

        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )

        # Completed section titles list (for progress tracking)
        completed_section_titles = []

        try:
            # Initialize: create report folder and save initial state
            ReportManager._ensure_report_folder(report_id)

            # Initialize logger (structured log agent_log.jsonl)
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )

            # Initialize console logger (console_log.txt)
            self.console_logger = ReportConsoleLogger(report_id)

            ReportManager.update_progress(
                report_id, "pending", 0, "Initializing report...",
                completed_sections=[]
            )
            ReportManager.save_report(report)

            # Phase 1: Plan outline
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Starting report outline planning...",
                completed_sections=[]
            )

            # Log planning start
            self.report_logger.log_planning_start()

            if progress_callback:
                progress_callback("planning", 0, "Starting report outline planning...")

            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg:
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline

            # Log planning complete
            self.report_logger.log_planning_complete(outline.to_dict())

            # Save outline to file
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"Outline planning complete, {len(outline.sections)} sections",
                completed_sections=[]
            )
            ReportManager.save_report(report)

            logger.info(f"Outline saved to file: {report_id}/outline.json")

            # Phase 2: Generate section by section (save each section)
            report.status = ReportStatus.GENERATING

            total_sections = len(outline.sections)
            generated_sections = []  # Save content for context

            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)

                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Generating section: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )

                if progress_callback:
                    progress_callback(
                        "generating",
                        base_progress,
                        f"Generating section: {section.title} ({section_num}/{total_sections})"
                    )

                # Generate main section content
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage,
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                section_content = self._finalize_section_text(section, section_content)

                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Save section
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # Log section complete
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"Section saved: {report_id}/section_{section_num:02d}.md")

                # Update progress
                ReportManager.update_progress(
                    report_id, "generating",
                    base_progress + int(70 / total_sections),
                    f"Section {section.title} completed",
                    current_section=None,
                    completed_sections=completed_section_titles
                )

            # Phase 3: Assemble complete report
            if progress_callback:
                progress_callback("generating", 95, "Assembling complete report...")

            ReportManager.update_progress(
                report_id, "generating", 95, "Assembling complete report...",
                completed_sections=completed_section_titles
            )

            # Use ReportManager to assemble complete report
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            evaluation_result = self._evaluate_report_quality(report.markdown_content, outline)
            ReportManager.save_evaluation(report_id, evaluation_result)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()

            # Calculate total elapsed time
            total_time_seconds = (datetime.now() - start_time).total_seconds()

            # Log report complete
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )

            # Save final report
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "Report generation complete",
                completed_sections=completed_section_titles
            )

            if progress_callback:
                progress_callback("completed", 100, "Report generation complete")

            logger.info(f"Report generation complete: {report_id}")

            # Close console logger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None

            return report

        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)

            # Record error log
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")

            # Save failed state
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"Report generation failed: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # Ignore save failure errors

            # Close console logger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None

            return report

    def chat(
        self,
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Chat with Report Agent

        In conversation, Agent can autonomously call retrieval tools to answer questions

        Args:
            message: User message
            chat_history: Chat history

        Returns:
            {
                "response": "Agent reply",
                "tool_calls": [List of called tools],
                "sources": [Information sources]
            }
        """
        logger.info(f"Report Agent chat: {message[:50]}...")

        chat_history = chat_history or []

        # Get generated report content
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Limit report length to avoid context overflow
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Report content truncated] ..."
        except Exception as e:
            logger.warning(f"Failed to get report content: {e}")

        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            temporal_context=self._build_temporal_report_context(),
            report_content=report_content if report_content else "(No report available)",
            tools_description=self._get_tools_description(),
        )

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        # Add chat history
        for h in chat_history[-10:]:  # Limit history length
            messages.append(h)

        # Add user message
        messages.append({
            "role": "user",
            "content": message
        })

        # ReACT loop (simplified)
        tool_calls_made = []
        max_iterations = 2  # Reduced iteration rounds

        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )

            # Parse tool calls
            tool_calls = self._parse_tool_calls(response)

            if not tool_calls:
                # No tool calls, return response directly
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                clean_response = self._ensure_chat_small_summary(clean_response)

                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }

            # Execute tool calls (limited count)
            tool_results = []
            for call in tool_calls[:1]:  # Max 1 tool call per round
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Limit result length
                })
                tool_calls_made.append(call)

            # Add results to messages
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']} result]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })

        # Reached max iterations, get final response
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        ) or ""

        # Clean response
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        clean_response = self._ensure_chat_small_summary(clean_response)

        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    Report Manager

    Responsible for report persistence and retrieval

    File structure (section-by-section output):
    reports/
      {report_id}/
        meta.json          - Report metadata and status
        outline.json       - Report outline
        progress.json      - Generation progress
        section_01.md      - Section 1
        section_02.md      - Section 2
        ...
        full_report.md     - Complete report
    """

    # Report storage directory
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')

    @classmethod
    def _ensure_reports_dir(cls):
        """Ensure reports root directory exists"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)

    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Get report folder path"""
        return os.path.join(cls.REPORTS_DIR, report_id)

    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Ensure report folder exists and return path"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder

    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Get report metadata file path"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")

    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Get complete report Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")

    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Get outline file path"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")

    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Get progress file path"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")

    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Get section Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")

    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Get Agent log file path"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")

    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Get console log file path"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")

    @classmethod
    def _get_evaluation_path(cls, report_id: str) -> str:
        """Get report quality evaluation path"""
        return os.path.join(cls._get_report_folder(report_id), "evaluation.json")

    @classmethod
    def save_evaluation(cls, report_id: str, evaluation: Dict[str, Any]) -> None:
        """Save deterministic report quality evaluation."""
        cls._ensure_report_folder(report_id)
        with open(cls._get_evaluation_path(report_id), "w", encoding="utf-8") as f:
            json.dump(evaluation, f, ensure_ascii=False, indent=2)

    @classmethod
    def get_evaluation(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Read report quality evaluation if available."""
        path = cls._get_evaluation_path(report_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get console log content

        These are console output logs during report generation (INFO, WARNING, etc.),
        different from the structured logs in agent_log.jsonl.

        Args:
            report_id: Report ID
            from_line: Start reading from this line (for incremental retrieval, 0 means from beginning)

        Returns:
            {
                "logs": [Log lines list],
                "total_lines": Total line count,
                "from_line": Starting line number,
                "has_more": Whether there are more logs
            }
        """
        log_path = cls._get_console_log_path(report_id)

        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }

        logs = []
        total_lines = 0

        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Keep original log line, remove trailing newline
                    logs.append(line.rstrip('\n\r'))

        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Read to end
        }

    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Get complete console log (all at once)

        Args:
            report_id: Report ID

        Returns:
            Log lines list
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]

    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get Agent log content

        Args:
            report_id: Report ID
            from_line: Start reading from this line (for incremental retrieval, 0 means from beginning)

        Returns:
            {
                "logs": [Log entries list],
                "total_lines": Total line count,
                "from_line": Starting line number,
                "has_more": Whether there are more logs
            }
        """
        log_path = cls._get_agent_log_path(report_id)

        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }

        logs = []
        total_lines = 0

        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Skip lines that failed to parse
                        continue

        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Read to end
        }

    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get complete Agent log (for fetching all at once)

        Args:
            report_id: Report ID

        Returns:
            Log entries list
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]

    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Save report outline

        Called immediately after planning phase is complete
        """
        cls._ensure_report_folder(report_id)

        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(f"Outline saved: {report_id}")

    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Save a single section

        Called immediately after each section generation is complete, enabling section-by-section output

        Args:
            report_id: Report ID
            section_index: Section index (starting from 1)
            section: Section object

        Returns:
            Saved file path
        """
        cls._ensure_report_folder(report_id)

        # Build section Markdown content - clean possible duplicate headings
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # Save file
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Section saved: {report_id}/{file_suffix}")
        return file_path

    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Clean section content

        1. Remove Markdown heading lines at content start that duplicate section title
        2. Convert all ### and lower level headings to bold text

        Args:
            content: Original content
            section_title: Section title

        Returns:
            Cleaned content
        """
        import re

        if not content:
            return content

        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Check if this is a Markdown heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)

            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()

                # Check if heading duplicates section title (skip duplicates in first 5 lines)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue

                # Convert all heading levels (#, ##, ###, #### etc.) to bold
                # Section titles are added by system, content should not have any headings
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Add blank line
                continue

            # If previous line was a skipped heading and current line is empty, also skip
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue

            skip_next_empty = False
            cleaned_lines.append(line)

        # Remove leading blank lines
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)

        # Remove leading separator lines
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # Also remove blank lines after separator
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)

        return '\n'.join(cleaned_lines)

    @classmethod
    def update_progress(
        cls,
        report_id: str,
        status: str,
        progress: int,
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Update report generation progress

        Frontend can get real-time progress by reading progress.json
        """
        cls._ensure_report_folder(report_id)

        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }

        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)

    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Get report generation progress"""
        path = cls._get_progress_path(report_id)

        if not os.path.exists(path):
            return None

        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get generated sections list

        Return all saved section file information
        """
        folder = cls._get_report_folder(report_id)

        if not os.path.exists(folder):
            return []

        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Parse section index from filename
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections

    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Assemble complete report

        Assemble complete report from saved section files with heading cleanup
        """
        folder = cls._get_report_folder(report_id)

        # Build report header
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"

        # Read all section files in order
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]

        # Post-process: clean heading issues in the entire report
        md_content = cls._post_process_report(md_content, outline)

        # Save complete report
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Complete report assembled: {report_id}")
        return md_content

    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Post-process report content

        1. Remove duplicate headings
        2. Keep report main title (#) and section titles (##), remove other heading levels (###, #### etc.)
        3. Clean excess blank lines and separator lines

        Args:
            content: Original report content
            outline: Report outline

        Returns:
            Processed content
        """
        import re

        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False

        # Collect all section titles from outline
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Check if this is a heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)

            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                # Check if this is a duplicate heading (same content heading within 5 consecutive lines)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break

                if is_duplicate:
                    # Skip duplicate heading and following blank lines
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue

                # Heading level handling:
                # - # (level=1) Keep only report main title
                # - ## (level=2) Keep section titles
                # - ### and below (level>=3) Convert to bold text

                if level == 1:
                    if title == outline.title:
                        # Keep report main title
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Section title incorrectly used #, correcting to ##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Other level-1 headings converted to bold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Keep section title
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Non-section level-2 headings converted to bold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # ### and lower level headings converted to bold text
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False

                i += 1
                continue

            elif stripped == '---' and prev_was_heading:
                # Skip separator line immediately after heading
                i += 1
                continue

            elif stripped == '' and prev_was_heading:
                # Keep only one blank line after heading
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False

            else:
                processed_lines.append(line)
                prev_was_heading = False

            i += 1

        # Clean consecutive multiple blank lines (keep max 2)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)

        return '\n'.join(result_lines)

    @classmethod
    def save_report(cls, report: Report) -> None:
        """Save report metadata and complete report"""
        cls._ensure_report_folder(report.report_id)

        # Save metadata JSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

        # Save outline
        if report.outline:
            cls.save_outline(report.report_id, report.outline)

        # Save complete Markdown report
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)

        logger.info(f"Report saved: {report.report_id}")

    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Get report"""
        path = cls._get_report_path(report_id)

        if not os.path.exists(path):
            # Backward compatible: check files stored directly in reports directory
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Rebuild Report object
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )

        # If markdown_content is empty, try reading from full_report.md
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()

        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )

    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Get report by simulation ID"""
        cls._ensure_reports_dir()

        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Backward compatible: JSON files
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report

        return None

    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """List reports"""
        cls._ensure_reports_dir()

        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Backward compatible: JSON files
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)

        # Sort by creation time descending
        reports.sort(key=lambda r: r.created_at, reverse=True)

        return reports[:limit]

    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Delete report (entire folder)"""
        import shutil

        folder_path = cls._get_report_folder(report_id)

        # New format: delete entire folder
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"Report folder deleted: {report_id}")
            return True

        # Backward compatible: delete individual files
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")

        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True

        return deleted
