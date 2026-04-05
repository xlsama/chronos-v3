from src.ops_agent.tools.service_connectors.mysql import MySQLConnector


class StarRocksConnector(MySQLConnector):
    service_type = "starrocks"
