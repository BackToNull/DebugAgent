"""
预处理模块 - 解析堆栈、提取实体、聚合日志
"""
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class StackFrame:
    """堆栈帧"""
    file: str
    line: int
    function: str
    code: Optional[str] = None
    is_framework: bool = False


@dataclass
class ParsedStackTrace:
    """解析后的堆栈信息"""
    exception_type: str
    exception_message: str
    frames: List[StackFrame]
    root_frame: Optional[StackFrame] = None  # 业务代码中最底层的帧


class StackParser:
    """堆栈解析器"""
    
    # Python 堆栈正则
    PYTHON_FRAME_PATTERN = re.compile(
        r'File "([^"]+)", line (\d+), in (\w+)'
    )
    PYTHON_EXCEPTION_PATTERN = re.compile(
        r'^(\w+(?:\.\w+)*(?:Error|Exception|Warning)?): (.+)$',
        re.MULTILINE
    )
    
    # Java 堆栈正则
    JAVA_FRAME_PATTERN = re.compile(
        r'at ([\w.$]+)\(([\w]+\.java):(\d+)\)'
    )
    JAVA_EXCEPTION_PATTERN = re.compile(
        r'^([\w.]+(?:Exception|Error)): (.+)$',
        re.MULTILINE
    )
    
    # 常见框架包名（用于识别框架层 vs 业务层）
    FRAMEWORK_PATTERNS = [
        r'site-packages',
        r'dist-packages',
        r'lib/python',
        r'java\.lang\.',
        r'java\.util\.',
        r'org\.springframework\.',
        r'com\.sun\.',
        r'sun\.',
        r'fastapi',
        r'starlette',
        r'uvicorn',
        r'asyncio',
        r'concurrent',
    ]
    
    def __init__(self, business_package: str = "copilot"):
        """
        Args:
            business_package: 业务代码包名，用于识别业务层堆栈
        """
        self.business_package = business_package
    
    def parse(self, stack_trace: str) -> ParsedStackTrace:
        """解析堆栈信息"""
        if not stack_trace:
            return ParsedStackTrace(
                exception_type="Unknown",
                exception_message="No stack trace provided",
                frames=[]
            )
        
        # 尝试 Python 格式
        frames = self._parse_python_frames(stack_trace)
        exception_type, exception_message = self._parse_python_exception(stack_trace)
        
        # 如果 Python 解析失败，尝试 Java 格式
        if not frames:
            frames = self._parse_java_frames(stack_trace)
            if frames:
                exception_type, exception_message = self._parse_java_exception(stack_trace)
        
        # 标记框架层
        for frame in frames:
            frame.is_framework = self._is_framework_code(frame.file)
        
        # 找到业务代码中最底层的帧
        root_frame = None
        for frame in reversed(frames):
            if not frame.is_framework:
                root_frame = frame
                break
        
        return ParsedStackTrace(
            exception_type=exception_type,
            exception_message=exception_message,
            frames=frames,
            root_frame=root_frame
        )
    
    def _parse_python_frames(self, stack_trace: str) -> List[StackFrame]:
        """解析 Python 堆栈帧"""
        frames = []
        lines = stack_trace.split('\n')
        
        for i, line in enumerate(lines):
            match = self.PYTHON_FRAME_PATTERN.search(line)
            if match:
                code = None
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith('File'):
                        code = next_line
                
                frames.append(StackFrame(
                    file=match.group(1),
                    line=int(match.group(2)),
                    function=match.group(3),
                    code=code
                ))
        
        return frames
    
    def _parse_java_frames(self, stack_trace: str) -> List[StackFrame]:
        """解析 Java 堆栈帧"""
        frames = []
        for match in self.JAVA_FRAME_PATTERN.finditer(stack_trace):
            frames.append(StackFrame(
                file=match.group(2),
                line=int(match.group(3)),
                function=match.group(1)
            ))
        return frames
    
    def _parse_python_exception(self, stack_trace: str) -> Tuple[str, str]:
        """提取 Python 异常类型和消息"""
        match = self.PYTHON_EXCEPTION_PATTERN.search(stack_trace)
        if match:
            return match.group(1), match.group(2)
        return "UnknownError", "Unable to parse exception"
    
    def _parse_java_exception(self, stack_trace: str) -> Tuple[str, str]:
        """提取 Java 异常类型和消息"""
        match = self.JAVA_EXCEPTION_PATTERN.search(stack_trace)
        if match:
            return match.group(1), match.group(2)
        return "UnknownException", "Unable to parse exception"
    
    def _is_framework_code(self, file_path: str) -> bool:
        """判断是否是框架代码"""
        for pattern in self.FRAMEWORK_PATTERNS:
            if re.search(pattern, file_path, re.IGNORECASE):
                return True
        return False
    
    def get_business_frames(self, parsed: ParsedStackTrace) -> List[StackFrame]:
        """获取业务代码相关的堆栈帧"""
        return [f for f in parsed.frames if not f.is_framework]


class EntityExtractor:
    """实体提取器 - 从错误信息中提取关键实体"""
    
    # 常见实体模式
    PATTERNS = {
        'trace_id': [
            r'trace[_-]?id[=:\s]+([a-zA-Z0-9-]+)',
            r'x-trace-id[=:\s]+([a-zA-Z0-9-]+)',
        ],
        'request_id': [
            r'request[_-]?id[=:\s]+([a-zA-Z0-9-]+)',
            r'req[_-]?id[=:\s]+([a-zA-Z0-9-]+)',
        ],
        'user_id': [
            r'user[_-]?id[=:\s]+([a-zA-Z0-9-]+)',
            r'uid[=:\s]+([a-zA-Z0-9-]+)',
        ],
        'error_code': [
            r'error[_-]?code[=:\s]+(\d+)',
            r'code[=:\s]+(\d{3,})',
            r'HTTP[/\s]+\d+\.\d+\s+(\d{3})',
        ],
        'api_endpoint': [
            r'(?:GET|POST|PUT|DELETE|PATCH)\s+(/[^\s]+)',
            r'endpoint[=:\s]+(/[^\s]+)',
            r'path[=:\s]+(/[^\s]+)',
        ],
        'service_name': [
            r'service[=:\s]+([a-zA-Z0-9_-]+)',
            r'from\s+([a-zA-Z0-9_-]+-service)',
        ],
        'timeout': [
            r'timeout[=:\s]+(\d+(?:\.\d+)?)\s*(?:s|ms)?',
            r'(\d+(?:\.\d+)?)\s*(?:seconds?|ms|milliseconds?)\s+timeout',
        ],
        'ip_address': [
            r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b',
        ],
        'port': [
            r':(\d{2,5})\b',
        ],
    }
    
    def extract(self, text: str) -> Dict[str, List[str]]:
        """从文本中提取所有实体"""
        entities = {}
        
        for entity_type, patterns in self.PATTERNS.items():
            matches = []
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    value = match.group(1)
                    if value not in matches:
                        matches.append(value)
            if matches:
                entities[entity_type] = matches
        
        return entities
    
    def extract_error_keywords(self, text: str) -> List[str]:
        """提取错误关键词"""
        keywords = []
        
        # 常见错误关键词
        error_patterns = [
            r'\b(timeout|timed?\s*out)\b',
            r'\b(connection\s+(?:refused|reset|closed|failed))\b',
            r'\b(null\s*pointer|none\s*type|undefined)\b',
            r'\b(out\s+of\s+memory|oom)\b',
            r'\b(rate\s*limit|throttl)',
            r'\b(auth(?:entication|orization)?\s+(?:failed|error))\b',
            r'\b(permission\s+denied|forbidden)\b',
            r'\b(not\s+found|404)\b',
            r'\b(internal\s+(?:server\s+)?error|500)\b',
            r'\b(bad\s+(?:request|gateway)|400|502)\b',
            r'\b(deadlock|race\s+condition)\b',
            r'\b(memory\s+leak)\b',
            r'\b(stack\s+overflow)\b',
        ]
        
        for pattern in error_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            keywords.extend(matches)
        
        return list(set(keywords))


class LogAggregator:
    """日志聚合器 - 基于 trace_id 等聚合相关日志"""
    
    def __init__(self):
        self.entity_extractor = EntityExtractor()
    
    def aggregate_by_trace(
        self, 
        logs: List[str], 
        trace_id: Optional[str] = None
    ) -> List[str]:
        """按 trace_id 聚合日志"""
        if not trace_id:
            return logs
        
        related_logs = []
        for log in logs:
            if trace_id in log:
                related_logs.append(log)
        
        return related_logs
    
    def sort_by_timestamp(self, logs: List[str]) -> List[str]:
        """按时间戳排序日志"""
        # 常见时间戳格式
        timestamp_patterns = [
            r'(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})',
            r'(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2})',
        ]
        
        def extract_timestamp(log: str) -> str:
            for pattern in timestamp_patterns:
                match = re.search(pattern, log)
                if match:
                    return match.group(1)
            return ""
        
        return sorted(logs, key=extract_timestamp)
    
    def extract_error_logs(self, logs: List[str]) -> List[str]:
        """提取错误级别的日志"""
        error_indicators = [
            r'\b(ERROR|FATAL|CRITICAL|SEVERE)\b',
            r'\b(Exception|Error|Failure)\b',
            r'\b(failed|failure|error)\b',
        ]
        
        error_logs = []
        for log in logs:
            for pattern in error_indicators:
                if re.search(pattern, log, re.IGNORECASE):
                    error_logs.append(log)
                    break
        
        return error_logs


class Preprocessor:
    """预处理器 - 组合各个子模块"""
    
    def __init__(self, business_package: str = "copilot"):
        self.stack_parser = StackParser(business_package)
        self.entity_extractor = EntityExtractor()
        self.log_aggregator = LogAggregator()
    
    def process(self, bug_input: Dict[str, Any]) -> Dict[str, Any]:
        """预处理 Bug 输入"""
        result = {
            "original": bug_input,
            "parsed_stack": None,
            "entities": {},
            "error_keywords": [],
            "aggregated_logs": [],
            "business_frames": [],
        }
        
        # 解析堆栈
        error_info = bug_input.get("error_info", {})
        stack_trace = error_info.get("stack_trace", "")
        if stack_trace:
            parsed = self.stack_parser.parse(stack_trace)
            result["parsed_stack"] = {
                "exception_type": parsed.exception_type,
                "exception_message": parsed.exception_message,
                "frames": [
                    {
                        "file": f.file,
                        "line": f.line,
                        "function": f.function,
                        "code": f.code,
                        "is_framework": f.is_framework
                    }
                    for f in parsed.frames
                ],
                "root_frame": {
                    "file": parsed.root_frame.file,
                    "line": parsed.root_frame.line,
                    "function": parsed.root_frame.function,
                } if parsed.root_frame else None
            }
            result["business_frames"] = [
                f for f in result["parsed_stack"]["frames"] 
                if not f["is_framework"]
            ]
        
        # 提取实体
        text_to_analyze = " ".join([
            error_info.get("error_message", ""),
            stack_trace,
            bug_input.get("context", {}).get("user_description", "") or "",
        ])
        result["entities"] = self.entity_extractor.extract(text_to_analyze)
        result["error_keywords"] = self.entity_extractor.extract_error_keywords(
            text_to_analyze
        )
        
        # 聚合日志
        related_logs = bug_input.get("related_logs", [])
        trace_id = error_info.get("trace_id")
        if related_logs:
            result["aggregated_logs"] = self.log_aggregator.aggregate_by_trace(
                related_logs, trace_id
            )
            result["aggregated_logs"] = self.log_aggregator.sort_by_timestamp(
                result["aggregated_logs"]
            )
        
        return result
