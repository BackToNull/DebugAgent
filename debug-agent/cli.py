"""
Debug Agent CLI - 命令行交互工具
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from datetime import datetime

from config.settings import settings
from src.models.schemas import (
    BugInput, 
    ErrorInfo, 
    BugContext, 
    EnvironmentInfo,
    BugSource,
    BugSeverity,
    HistoryCase,
    CaseProblem,
    CaseResolution,
    FixType
)
from src.service import DebugAgentService

console = Console()


def get_service() -> DebugAgentService:
    """获取服务实例"""
    if not settings.openai_api_key:
        console.print("[red]Error: OPENAI_API_KEY not set. Please configure in .env file[/red]")
        sys.exit(1)
    
    return DebugAgentService(
        openai_api_key=settings.openai_api_key,
        llm_model=settings.llm_model,
        openai_base_url=settings.openai_base_url,
        chroma_persist_dir=settings.chroma_persist_dir
    )


@click.group()
def cli():
    """Debug Agent - 智能 Bug 分析工具"""
    pass


@cli.command()
@click.option('--error', '-e', required=True, help='错误信息')
@click.option('--stack', '-s', default=None, help='堆栈信息（可选）')
@click.option('--trace-id', '-t', default=None, help='Trace ID（可选）')
@click.option('--description', '-d', default=None, help='问题描述（可选）')
@click.option('--severity', type=click.Choice(['P0', 'P1', 'P2', 'P3']), default='P2', help='严重程度')
@click.option('--output', '-o', type=click.Choice(['rich', 'json']), default='rich', help='输出格式')
def analyze(error: str, stack: str, trace_id: str, description: str, severity: str, output: str):
    """分析 Bug"""
    console.print("\n[bold blue]🔍 Debug Agent - Bug 分析[/bold blue]\n")
    
    # 构建输入
    bug_input = BugInput(
        source=BugSource.MANUAL,
        severity=BugSeverity(severity),
        environment=EnvironmentInfo(service="copilot-server"),
        error_info=ErrorInfo(
            error_message=error,
            stack_trace=stack,
            trace_id=trace_id
        ),
        context=BugContext(user_description=description) if description else None
    )
    
    # 显示输入信息
    console.print(Panel(f"[yellow]错误信息:[/yellow] {error}", title="📥 输入"))
    
    with console.status("[bold green]正在分析...[/bold green]"):
        service = get_service()
        result = asyncio.run(service.analyze_bug(bug_input))
    
    # 输出结果
    if output == 'json':
        console.print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False, default=str))
    else:
        display_result(result)


def display_result(result):
    """富文本显示分析结果"""
    # 总结
    console.print(Panel(
        f"[bold]{result.summary}[/bold]",
        title="📋 问题总结",
        border_style="green"
    ))
    
    # 根因分析
    root_cause = result.root_cause
    confidence_color = "green" if root_cause.confidence > 0.7 else "yellow" if root_cause.confidence > 0.4 else "red"
    console.print(Panel(
        f"[bold]分类:[/bold] {root_cause.category.value}\n"
        f"[bold]置信度:[/bold] [{confidence_color}]{root_cause.confidence:.0%}[/{confidence_color}]\n\n"
        f"{root_cause.description}",
        title="🔍 根因分析",
        border_style="blue"
    ))
    
    # 代码定位
    if result.location:
        loc = result.location
        console.print(Panel(
            f"[bold]文件:[/bold] {loc.file}\n"
            f"[bold]行号:[/bold] {loc.line_start}" + (f"-{loc.line_end}" if loc.line_end else "") + "\n"
            f"[bold]函数:[/bold] {loc.function or 'N/A'}",
            title="📍 代码定位",
            border_style="cyan"
        ))
    
    # 修复建议
    fix = result.fix_suggestion
    fix_content = f"[bold]类型:[/bold] {fix.fix_type.value}\n\n{fix.description}"
    if fix.code_diff:
        fix_content += f"\n\n[bold]代码修改:[/bold]\n```diff\n{fix.code_diff}\n```"
    if fix.test_verification:
        fix_content += f"\n\n[bold]验证方法:[/bold] {fix.test_verification}"
    
    console.print(Panel(
        Markdown(fix_content.replace("[bold]", "**").replace("[/bold]", "**")),
        title="💡 修复建议",
        border_style="yellow"
    ))
    
    # 影响评估
    impact = result.impact_assessment
    console.print(Panel(
        f"[bold]紧急程度:[/bold] {impact.urgency.value}\n"
        f"[bold]影响范围:[/bold] {impact.affected_users or '未知'}\n"
        f"[bold]影响功能:[/bold] {', '.join(impact.affected_features) or '未知'}",
        title="⚠️ 影响评估",
        border_style="red"
    ))
    
    # 相似案例
    if result.similar_cases:
        table = Table(title="📚 相似历史案例")
        table.add_column("案例ID", style="cyan")
        table.add_column("标题", style="white")
        table.add_column("相似度", style="green")
        
        for case in result.similar_cases:
            table.add_row(
                case.case_id,
                case.title[:50] + "..." if len(case.title) > 50 else case.title,
                f"{case.similarity:.0%}"
            )
        
        console.print(table)
    
    # 进一步排查建议
    if result.additional_investigation:
        console.print(Panel(
            "\n".join(f"• {item}" for item in result.additional_investigation),
            title="🔎 进一步排查建议",
            border_style="magenta"
        ))
    
    console.print(f"\n[dim]分析ID: {result.analysis_id}[/dim]\n")


@cli.command()
@click.option('--title', '-t', required=True, help='Case 标题')
@click.option('--description', '-d', required=True, help='问题描述')
@click.option('--root-cause', '-r', required=True, help='根因')
@click.option('--fix', '-f', required=True, help='修复方案')
@click.option('--fix-type', type=click.Choice(['code_change', 'config_change', 'rollback']), default='code_change')
@click.option('--tags', help='标签，逗号分隔')
def add_case(title: str, description: str, root_cause: str, fix: str, fix_type: str, tags: str):
    """添加历史 Case 到知识库"""
    console.print("\n[bold blue]📝 添加历史 Case[/bold blue]\n")
    
    case = HistoryCase(
        case_id=f"CASE-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        created_at=datetime.now(),
        problem=CaseProblem(
            title=title,
            description=description
        ),
        resolution=CaseResolution(
            root_cause=root_cause,
            fix_type=FixType(fix_type),
            fix_detail=fix
        ),
        tags=tags.split(',') if tags else []
    )
    
    service = get_service()
    service.add_history_case(case)
    
    console.print(f"[green]✅ Case 添加成功: {case.case_id}[/green]")


@cli.command()
def stats():
    """查看知识库统计"""
    console.print("\n[bold blue]📊 知识库统计[/bold blue]\n")
    
    service = get_service()
    stats = service.get_knowledge_stats()
    
    table = Table(title="知识库统计")
    table.add_column("类型", style="cyan")
    table.add_column("数量", style="green", justify="right")
    
    table.add_row("代码片段", str(stats.get("code_snippets", 0)))
    table.add_row("历史 Case", str(stats.get("history_cases", 0)))
    table.add_row("日志模式", str(stats.get("log_patterns", 0)))
    
    console.print(table)


@cli.command()
def interactive():
    """交互式分析模式"""
    console.print("\n[bold blue]🤖 Debug Agent 交互模式[/bold blue]")
    console.print("[dim]输入 'quit' 或 'exit' 退出[/dim]\n")
    
    service = get_service()
    
    while True:
        try:
            error_msg = console.input("[bold yellow]请输入错误信息:[/bold yellow] ")
            
            if error_msg.lower() in ['quit', 'exit', 'q']:
                console.print("[dim]👋 再见！[/dim]")
                break
            
            if not error_msg.strip():
                continue
            
            # 可选：堆栈信息
            stack = console.input("[dim]堆栈信息（可选，直接回车跳过）:[/dim] ") or None
            
            # 可选：描述
            desc = console.input("[dim]问题描述（可选，直接回车跳过）:[/dim] ") or None
            
            bug_input = BugInput(
                source=BugSource.MANUAL,
                error_info=ErrorInfo(
                    error_message=error_msg,
                    stack_trace=stack
                ),
                context=BugContext(user_description=desc) if desc else None
            )
            
            with console.status("[bold green]正在分析...[/bold green]"):
                result = asyncio.run(service.analyze_bug(bug_input))
            
            display_result(result)
            console.print("\n" + "="*60 + "\n")
            
        except KeyboardInterrupt:
            console.print("\n[dim]👋 再见！[/dim]")
            break
        except Exception as e:
            console.print(f"[red]分析出错: {e}[/red]")


@cli.command()
def serve():
    """启动 API 服务"""
    import uvicorn
    console.print(f"\n[bold blue]🚀 启动 Debug Agent API 服务[/bold blue]")
    console.print(f"[dim]地址: http://{settings.api_host}:{settings.api_port}[/dim]")
    console.print(f"[dim]文档: http://{settings.api_host}:{settings.api_port}/docs[/dim]\n")
    
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )


if __name__ == "__main__":
    cli()
