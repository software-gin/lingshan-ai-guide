"""
==============================================================
知识图谱构建脚本（GraphRAG 离线建图，命令行手动执行）
==============================================================
从知识库逐条抽取 (头实体, 关系, 尾实体) 三元组并持久化，
构建完成后检索链路自动附带图谱关联上下文。

用法（在 backend 目录下）：
    .venv\\Scripts\\python.exe scripts\\build_graph.py              # 全量建图
    .venv\\Scripts\\python.exe scripts\\build_graph.py --limit 10   # 试跑前 10 条
==============================================================
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(HERE)
sys.path.insert(0, BACKEND_ROOT)


def main():
    parser = argparse.ArgumentParser(description="灵山知识图谱构建（GraphRAG）")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 条知识（试跑用）")
    args = parser.parse_args()

    from app import create_app
    from models import Knowledge, KnowledgeTriple
    from services.graph_service import get_knowledge_graph

    app = create_app()
    with app.app_context():
        total_k = Knowledge.query.filter_by(is_active=True).count()
        scope = f"限 {args.limit} 条" if args.limit else "全量"
        print(f"[Graph] 知识库共 {total_k} 条有效条目，开始建图（{scope}）")

        count = get_knowledge_graph().build(limit=args.limit)

        entities = set()
        for t in KnowledgeTriple.query.filter_by(is_active=True).all():
            entities.add(t.head)
            entities.add(t.tail)
        print(f"[Graph] 完成：本次写入 {count} 条三元组；图谱现有实体 {len(entities)} 个")


if __name__ == "__main__":
    main()
