from langgraph.graph import END,StateGraph
from .nodes import collect_changes_node,identify_services_node,analyze_changes_node,identify_tests_node,determine_severity_node,llm_review_node,generate_report_node
from .state import ImpactAnalysisState
def build_graph():
    graph=StateGraph(ImpactAnalysisState)
    graph.add_node("collect_changes",collect_changes_node);graph.add_node("identify_services",identify_services_node);graph.add_node("analyze_changes",analyze_changes_node);graph.add_node("identify_tests",identify_tests_node);graph.add_node("determine_severity",determine_severity_node);graph.add_node("llm_review",llm_review_node);graph.add_node("generate_report",generate_report_node)
    graph.set_entry_point("collect_changes");graph.add_edge("collect_changes","identify_services");graph.add_edge("identify_services","analyze_changes");graph.add_edge("analyze_changes","identify_tests");graph.add_edge("identify_tests","determine_severity");graph.add_edge("determine_severity","llm_review");graph.add_edge("llm_review","generate_report");graph.add_edge("generate_report",END)
    return graph.compile()
agent=build_graph()
