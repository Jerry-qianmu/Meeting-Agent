#!/usr/bin/env python3
"""
检查 Milvus 运行状态的脚本
使用方法: python check_milvus.py
"""

import sys
import socket
from pymilvus import connections, utility, MilvusException

def check_port(host='localhost', port=19530, timeout=2):
    """检查端口是否可连接"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"端口检查异常: {e}")
        return False

def check_milvus(host='localhost', port=19530, timeout=10):
    """检查 Milvus 服务状态"""
    print(f"🔍 正在检查 Milvus 服务: {host}:{port}")
    print("-" * 50)
    
    # 1. 检查端口
    print("1️⃣ 检查端口连通性...")
    if not check_port(host, port):
        print(f"   ❌ 端口 {port} 无法连接")
        print(f"   💡 请确保 Milvus 已启动: docker ps | grep milvus")
        return False
    print(f"   ✅ 端口 {port} 可访问")
    
    # 2. 尝试连接
    print("\n2️⃣ 尝试建立连接...")
    try:
        connections.connect(
            alias="default",
            host=host,
            port=port,
            timeout=timeout
        )
        print("   ✅ 连接成功")
    except MilvusException as e:
        print(f"   ❌ 连接失败: {e}")
        return False
    except Exception as e:
        print(f"   ❌ 未知错误: {e}")
        return False
    
    # 3. 获取服务信息
    print("\n3️⃣ 获取服务信息...")
    try:
        # 检查服务版本
        version = utility.get_server_version()
        print(f"   ✅ Milvus 版本: {version}")
        
        # 检查服务状态
        print(f"   ✅ 服务状态: 运行中")
        
        # 获取集合列表
        collections = utility.list_collections()
        print(f"   📊 集合数量: {len(collections)}")
        if collections:
            print(f"   📋 集合列表: {', '.join(collections)}")
        
        # 检查是否有加载的集合
        loaded = []
        for col in collections:
            if utility.load_state(col) == "Loaded":
                loaded.append(col)
        if loaded:
            print(f"   🔥 已加载集合: {', '.join(loaded)}")
        
        return True
        
    except MilvusException as e:
        print(f"   ❌ 获取信息失败: {e}")
        return False
    except Exception as e:
        print(f"   ❌ 未知错误: {e}")
        return False

def main():
    # 可以自定义主机和端口
    host = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 19530
    
    print("=" * 50)
    print("Milvus 健康检查工具")
    print("=" * 50)
    
    if check_milvus(host, port):
        print("\n" + "=" * 50)
        print("✅ Milvus 服务运行正常")
        print("=" * 50)
        sys.exit(0)
    else:
        print("\n" + "=" * 50)
        print("❌ Milvus 服务不可用")
        print("=" * 50)
        print("\n💡 排查建议:")
        print("   1. 启动 Milvus: docker start milvus_standalone")
        print("   2. 查看日志: docker logs milvus_standalone")
        print("   3. 重启服务: docker restart milvus_standalone")
        sys.exit(1)

if __name__ == "__main__":
    main()