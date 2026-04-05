from src.ops_agent.tools.service_connectors.mysql import MySQLConnector


class DorisConnector(MySQLConnector):
    service_type = "doris"
