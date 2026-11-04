#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量提取 Fusion 360 API 文档

这个脚本需要在 Fusion 360 的 Python 环境中运行（通过 MCP 调用）
它会提取所有 API 的完整清单，包括类、方法、属性等信息
"""

import json
import inspect
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List


def extract_all_api_registry() -> Dict[str, Any]:
    """
    提取所有 Fusion 360 API 的完整清单

    返回包含所有命名空间、类、方法、属性的结构化数据
    """
    import adsk.core
    import adsk.fusion

    registry = {
        "extracted_at": datetime.now().isoformat(),
        "fusion360_version": None,  # 可以从 app.version 获取
        "namespaces": {},
        "statistics": {
            "total_namespaces": 0,
            "total_classes": 0,
            "total_methods": 0,
            "total_properties": 0
        }
    }

    try:
        app = adsk.core.Application.get()
        registry["fusion360_version"] = app.version
    except:
        pass

    # 遍历 adsk 的所有子模块
    import adsk
    for namespace_name in dir(adsk):
        if namespace_name.startswith('_'):
            continue

        namespace = getattr(adsk, namespace_name, None)
        if not inspect.ismodule(namespace):
            continue

        print(f"扫描命名空间: adsk.{namespace_name}")
        namespace_data = extract_namespace(namespace, namespace_name)

        if namespace_data["classes"]:
            registry["namespaces"][namespace_name] = namespace_data
            registry["statistics"]["total_namespaces"] += 1
            registry["statistics"]["total_classes"] += len(namespace_data["classes"])
            registry["statistics"]["total_methods"] += namespace_data["statistics"]["methods"]
            registry["statistics"]["total_properties"] += namespace_data["statistics"]["properties"]

    return registry


def extract_namespace(namespace, namespace_name: str) -> Dict[str, Any]:
    """提取单个命名空间的信息"""
    namespace_data = {
        "name": namespace_name,
        "full_name": f"adsk.{namespace_name}",
        "classes": {},
        "statistics": {
            "classes": 0,
            "methods": 0,
            "properties": 0
        }
    }

    # 遍历命名空间中的所有类
    for item_name in dir(namespace):
        if item_name.startswith('_'):
            continue

        try:
            item = getattr(namespace, item_name)
            if not inspect.isclass(item):
                continue

            class_data = extract_class(item, item_name, namespace_name)
            namespace_data["classes"][item_name] = class_data

            namespace_data["statistics"]["classes"] += 1
            namespace_data["statistics"]["methods"] += len(class_data["methods"])
            namespace_data["statistics"]["properties"] += len(class_data["properties"])

        except Exception as e:
            print(f"  跳过 {item_name}: {e}")
            continue

    return namespace_data


def extract_class(class_obj, class_name: str, namespace_name: str) -> Dict[str, Any]:
    """提取单个类的详细信息"""
    class_data = {
        "name": class_name,
        "namespace": f"adsk.{namespace_name}",
        "full_name": f"adsk.{namespace_name}.{class_name}",
        "doc": get_clean_doc(class_obj.__doc__),
        "properties": [],
        "methods": [],
        "static_methods": [],
        "class_methods": []
    }

    # 遍历类的所有成员
    for member_name in dir(class_obj):
        if member_name.startswith('_'):
            continue

        # 跳过 SWIG 生成的特殊成员
        if member_name in ["thisown", "cast"]:
            continue

        try:
            member = getattr(class_obj, member_name)

            # 属性
            if isinstance(member, property):
                prop_data = extract_property(member, member_name)
                class_data["properties"].append(prop_data)

            # 方法
            elif callable(member):
                method_data = extract_method(member, member_name, class_name)

                # 区分静态方法、类方法、实例方法
                if isinstance(inspect.getattr_static(class_obj, member_name), staticmethod):
                    class_data["static_methods"].append(method_data)
                elif isinstance(inspect.getattr_static(class_obj, member_name), classmethod):
                    class_data["class_methods"].append(method_data)
                else:
                    class_data["methods"].append(method_data)

        except Exception as e:
            # 某些成员可能无法访问
            continue

    return class_data


def extract_property(prop, prop_name: str) -> Dict[str, Any]:
    """提取属性信息"""
    prop_data = {
        "name": prop_name,
        "type": "property",
        "doc": get_clean_doc(prop.__doc__),
        "readonly": prop.fset is None,
        "writable": prop.fset is not None
    }

    # 尝试从文档中提取类型信息
    if prop_data["doc"]:
        type_hint = extract_type_from_doc(prop_data["doc"])
        if type_hint:
            prop_data["value_type"] = type_hint

    return prop_data


def extract_method(method, method_name: str, class_name: str) -> Dict[str, Any]:
    """提取方法信息"""
    method_data = {
        "name": method_name,
        "type": "method",
        "doc": get_clean_doc(method.__doc__)
    }

    # 提取方法签名
    try:
        sig = inspect.signature(method)
        sig_str = str(sig)

        # 清理签名字符串
        sig_str = sig_str.replace("(self, ", "(").replace("(self)", "()")
        sig_str = sig_str.replace("'", "").replace("::", ".")

        # 移除 SWIG 包装类型
        import re
        sig_str = re.sub(r'adsk\.core\.Ptr<([^>]+)>', r'\1', sig_str)

        method_data["signature"] = sig_str

        # 提取参数列表
        params = []
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue

            param_info = {"name": param_name}

            if param.annotation != inspect.Parameter.empty:
                param_info["type"] = str(param.annotation)

            if param.default != inspect.Parameter.empty:
                param_info["default"] = str(param.default)

            params.append(param_info)

        if params:
            method_data["parameters"] = params

        # 提取返回类型
        if sig.return_annotation != inspect.Signature.empty:
            method_data["return_type"] = str(sig.return_annotation)

    except Exception as e:
        # 某些方法可能无法提取签名
        method_data["signature_error"] = str(e)

    return method_data


def get_clean_doc(doc: str) -> str:
    """清理文档字符串"""
    if not doc:
        return ""

    # 移除多余的空白
    lines = [line.strip() for line in doc.split('\n')]
    lines = [line for line in lines if line]

    return ' '.join(lines)[:1000]  # 限制长度


def extract_type_from_doc(doc: str) -> str:
    """从文档中提取类型信息"""
    import re

    # 尝试匹配常见的类型标注模式
    patterns = [
        r'Returns\s+(?:a\s+)?(\w+)',
        r':\s*(\w+)',
        r'Type:\s*(\w+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, doc, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def save_registry(registry: Dict[str, Any], output_path: str):
    """保存清单到文件"""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 清单已保存到: {output_file}")
    print(f"   文件大小: {output_file.stat().st_size / 1024:.1f} KB")


def print_statistics(registry: Dict[str, Any]):
    """打印统计信息"""
    stats = registry["statistics"]

    print("\n" + "="*60)
    print("📊 提取统计")
    print("="*60)
    print(f"命名空间: {stats['total_namespaces']}")
    print(f"类:       {stats['total_classes']}")
    print(f"方法:     {stats['total_methods']}")
    print(f"属性:     {stats['total_properties']}")
    print("="*60)

    print("\n📋 各命名空间详情:")
    for ns_name, ns_data in registry["namespaces"].items():
        ns_stats = ns_data["statistics"]
        print(f"  adsk.{ns_name}:")
        print(f"    类: {ns_stats['classes']}, "
              f"方法: {ns_stats['methods']}, "
              f"属性: {ns_stats['properties']}")


def main():
    """主函数"""
    print("🚀 开始提取 Fusion 360 API 文档...")
    print("=" * 60)

    # 提取清单
    registry = extract_all_api_registry()

    # 打印统计
    print_statistics(registry)

    # 保存到文件
    output_path = "fusion360_api_registry.json"
    save_registry(registry, output_path)

    print("\n✅ 提取完成！")

    return registry


if __name__ == "__main__":
    main()
