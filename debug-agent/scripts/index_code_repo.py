"""
代码仓索引脚本 - 将代码仓中的代码片段索引到知识库
"""
import sys
from pathlib import Path
import os
import hashlib

sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import List, Dict, Any, Optional
from src.storage.vector_store import VectorStore


# 支持的代码文件扩展名
CODE_EXTENSIONS = {
    '.py': 'python',
    '.js': 'javascript',
    '.ts': 'typescript',
    '.jsx': 'javascript',
    '.tsx': 'typescript',
    '.go': 'go',
    '.java': 'java',
    '.rs': 'rust',
    '.cpp': 'cpp',
    '.c': 'c',
    '.h': 'c',
    '.hpp': 'cpp',
    '.rb': 'ruby',
    '.php': 'php',
    '.scala': 'scala',
    '.kt': 'kotlin',
    '.swift': 'swift',
}

# 忽略的目录
IGNORE_DIRS = {
    'node_modules', 'venv', '.venv', 'env', '.env',
    '__pycache__', '.git', '.svn', '.hg',
    'dist', 'build', 'target', 'out', 'bin',
    '.idea', '.vscode', '.pytest_cache',
    'vendor', 'packages', '.tox',
}

# 忽略的文件模式
IGNORE_FILES = {
    '__init__.py',  # 通常是空的或只有导入
    'setup.py',
    'conftest.py',
}


class CodeChunker:
    """代码切分器 - 按函数/类切分代码"""
    
    def __init__(
        self,
        max_chunk_size: int = 1500,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100
    ):
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    def chunk_file(self, file_path: str, content: str) -> List[Dict[str, Any]]:
        """
        将文件内容切分成多个片段
        
        Args:
            file_path: 文件路径
            content: 文件内容
            
        Returns:
            切分后的代码片段列表
        """
        ext = Path(file_path).suffix.lower()
        language = CODE_EXTENSIONS.get(ext, 'text')
        
        # 先尝试按函数/类切分
        chunks = self._chunk_by_structure(content, language)
        
        # 如果结构切分失败或块太大，使用行切分
        final_chunks = []
        for chunk in chunks:
            if len(chunk['content']) > self.max_chunk_size:
                # 大块需要进一步切分
                sub_chunks = self._chunk_by_lines(chunk['content'], chunk['start_line'])
                final_chunks.extend(sub_chunks)
            elif len(chunk['content']) >= self.min_chunk_size:
                final_chunks.append(chunk)
        
        # 为每个块添加文件路径信息
        for chunk in final_chunks:
            chunk['file_path'] = file_path
            chunk['language'] = language
            chunk['id'] = self._generate_chunk_id(file_path, chunk['start_line'])
        
        return final_chunks
    
    def _chunk_by_structure(self, content: str, language: str) -> List[Dict[str, Any]]:
        """按代码结构切分（函数、类等）"""
        chunks = []
        lines = content.split('\n')
        
        if language == 'python':
            chunks = self._chunk_python(lines)
        else:
            # 其他语言使用通用切分
            chunks = self._chunk_generic(lines)
        
        return chunks
    
    def _chunk_python(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Python 代码切分"""
        chunks = []
        current_chunk_lines = []
        current_start_line = 1
        in_class_or_func = False
        indent_level = 0
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # 检测函数或类定义
            if stripped.startswith(('def ', 'class ', 'async def ')):
                # 保存之前的块
                if current_chunk_lines and len('\n'.join(current_chunk_lines)) >= self.min_chunk_size:
                    chunks.append({
                        'content': '\n'.join(current_chunk_lines),
                        'start_line': current_start_line,
                        'end_line': i - 1,
                        'type': 'function' if 'def ' in '\n'.join(current_chunk_lines) else 'code'
                    })
                
                current_chunk_lines = [line]
                current_start_line = i
                in_class_or_func = True
                indent_level = len(line) - len(line.lstrip())
            
            elif in_class_or_func:
                current_chunk_lines.append(line)
                
                # 检测块是否结束（遇到同级或更低缩进的非空行）
                if stripped and not stripped.startswith('#'):
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent <= indent_level and not stripped.startswith(('def ', 'class ', 'async def ', '@')):
                        # 块结束
                        if len('\n'.join(current_chunk_lines)) >= self.min_chunk_size:
                            chunks.append({
                                'content': '\n'.join(current_chunk_lines[:-1]),
                                'start_line': current_start_line,
                                'end_line': i - 1,
                                'type': 'function'
                            })
                        current_chunk_lines = [line]
                        current_start_line = i
                        in_class_or_func = False
            else:
                current_chunk_lines.append(line)
        
        # 保存最后一个块
        if current_chunk_lines and len('\n'.join(current_chunk_lines)) >= self.min_chunk_size:
            chunks.append({
                'content': '\n'.join(current_chunk_lines),
                'start_line': current_start_line,
                'end_line': len(lines),
                'type': 'code'
            })
        
        return chunks if chunks else [{'content': '\n'.join(lines), 'start_line': 1, 'end_line': len(lines), 'type': 'file'}]
    
    def _chunk_generic(self, lines: List[str]) -> List[Dict[str, Any]]:
        """通用代码切分"""
        # 简单按行数切分
        content = '\n'.join(lines)
        return [{
            'content': content,
            'start_line': 1,
            'end_line': len(lines),
            'type': 'file'
        }]
    
    def _chunk_by_lines(self, content: str, base_line: int = 1) -> List[Dict[str, Any]]:
        """按行数切分大块"""
        chunks = []
        lines = content.split('\n')
        
        # 计算每块大约多少行
        avg_line_length = len(content) / max(len(lines), 1)
        lines_per_chunk = int(self.max_chunk_size / max(avg_line_length, 1))
        lines_per_chunk = max(lines_per_chunk, 20)  # 至少20行
        
        overlap_lines = int(self.chunk_overlap / max(avg_line_length, 1))
        
        start = 0
        while start < len(lines):
            end = min(start + lines_per_chunk, len(lines))
            chunk_lines = lines[start:end]
            chunk_content = '\n'.join(chunk_lines)
            
            if len(chunk_content) >= self.min_chunk_size:
                chunks.append({
                    'content': chunk_content,
                    'start_line': base_line + start,
                    'end_line': base_line + end - 1,
                    'type': 'chunk'
                })
            
            start = end - overlap_lines if end < len(lines) else end
        
        return chunks
    
    def _generate_chunk_id(self, file_path: str, start_line: int) -> str:
        """生成唯一的 chunk ID"""
        content = f"{file_path}:{start_line}"
        return hashlib.md5(content.encode()).hexdigest()[:16]


class CodeIndexer:
    """代码索引器"""
    
    def __init__(
        self,
        vector_store: VectorStore,
        chunker: Optional[CodeChunker] = None
    ):
        self.vector_store = vector_store
        self.chunker = chunker or CodeChunker()
    
    def index_repository(
        self,
        repo_path: str,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> Dict[str, int]:
        """
        索引整个代码仓
        
        Args:
            repo_path: 仓库路径
            include_patterns: 包含的文件模式（可选）
            exclude_patterns: 排除的文件模式（可选）
            
        Returns:
            索引统计
        """
        repo_path = Path(repo_path)
        if not repo_path.exists():
            raise ValueError(f"仓库路径不存在: {repo_path}")
        
        stats = {
            'files_scanned': 0,
            'files_indexed': 0,
            'chunks_created': 0,
            'errors': 0
        }
        
        # 遍历所有代码文件
        for file_path in self._find_code_files(repo_path):
            stats['files_scanned'] += 1
            
            try:
                # 读取文件内容
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # 跳过空文件或太大的文件
                if not content.strip() or len(content) > 100000:
                    continue
                
                # 切分代码
                rel_path = str(file_path.relative_to(repo_path))
                chunks = self.chunker.chunk_file(rel_path, content)
                
                if chunks:
                    # 索引到向量数据库
                    self._index_chunks(chunks)
                    stats['files_indexed'] += 1
                    stats['chunks_created'] += len(chunks)
                    
                    print(f"  ✓ {rel_path} ({len(chunks)} chunks)")
                    
            except Exception as e:
                stats['errors'] += 1
                print(f"  ✗ {file_path}: {e}")
        
        return stats
    
    def _find_code_files(self, repo_path: Path) -> List[Path]:
        """查找所有代码文件"""
        code_files = []
        
        for root, dirs, files in os.walk(repo_path):
            # 过滤忽略的目录
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
            
            for file in files:
                if file in IGNORE_FILES:
                    continue
                
                file_path = Path(root) / file
                ext = file_path.suffix.lower()
                
                if ext in CODE_EXTENSIONS:
                    code_files.append(file_path)
        
        return code_files
    
    def _index_chunks(self, chunks: List[Dict[str, Any]]):
        """将代码片段索引到向量数据库"""
        snippets = []
        for chunk in chunks:
            snippets.append({
                'id': chunk['id'],
                'content': chunk['content'],
                'metadata': {
                    'file_path': chunk['file_path'],
                    'language': chunk['language'],
                    'start_line': chunk['start_line'],
                    'end_line': chunk['end_line'],
                    'type': chunk.get('type', 'code')
                }
            })
        
        self.vector_store.add_code_snippets(snippets)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='索引代码仓到知识库')
    parser.add_argument('repo_path', nargs='?', help='代码仓路径')
    parser.add_argument('--clear', action='store_true', help='清空现有代码索引')
    args = parser.parse_args()
    
    # 从环境变量或参数获取路径
    repo_path = args.repo_path
    if not repo_path:
        from config.settings import settings
        repo_path = settings.code_repo_path
    
    if not repo_path:
        print("❌ 请指定代码仓路径:")
        print("   python scripts/index_code_repo.py /path/to/copilot-server")
        print("   或在 .env 中设置 CODE_REPO_PATH")
        sys.exit(1)
    
    print(f"🚀 索引代码仓: {repo_path}\n")
    
    # 初始化
    vector_store = VectorStore(persist_directory="./data/chroma")
    
    # 清空现有索引
    if args.clear:
        print("🗑️  清空现有代码索引...")
        vector_store.clear_collection("code_snippets")
    
    # 索引代码
    indexer = CodeIndexer(vector_store)
    stats = indexer.index_repository(repo_path)
    
    # 打印统计
    print(f"\n📊 索引完成:")
    print(f"   - 扫描文件: {stats['files_scanned']}")
    print(f"   - 索引文件: {stats['files_indexed']}")
    print(f"   - 创建片段: {stats['chunks_created']}")
    print(f"   - 错误: {stats['errors']}")
    
    # 总体统计
    all_stats = vector_store.get_stats()
    print(f"\n📚 知识库总计:")
    print(f"   - 代码片段: {all_stats['code_snippets']}")
    print(f"   - 历史 Case: {all_stats['history_cases']}")
    print(f"   - 日志模式: {all_stats['log_patterns']}")


if __name__ == "__main__":
    main()
