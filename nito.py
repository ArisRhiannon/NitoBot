"""NitoScript v0.2.0 — a comfy, deterministic Block-and-Chain language.

Everything turns around `Nito`: the empty value, the origin of all state, and the
absence that propagates safely through any operation (collapse it with `or`).

This module is the language core: lexer -> parser -> compiler -> NitoSupremeExecutor
(the deterministic bytecode VM). Blocks (functions) and the `|>` flow operator are
implemented here; State Chains and verify-by-replay arrive in later 0.2.0 phases.
"""
import sys
import io
import hashlib
from contextlib import redirect_stdout
from enum import Enum, auto
from typing import List, Dict, Set, Optional, Any

__version__ = "0.2.1"

# ==============================================================================
# FFI SECURITY ALLOWLIST
# ==============================================================================
# `use` maps Python callables into the VM. Restrict it to pure, side-effect-free
# numeric/utility targets so it can never become a remote-code-execution primitive.
ALLOWED_FFI_MODULES: Set[str] = {"math", "random", "statistics"}
ALLOWED_FFI_BUILTINS: Set[str] = {
    "abs", "round", "min", "max", "sum", "len", "pow", "divmod",
    "int", "float", "str", "bool", "ord", "chr", "sorted", "range",
}

# ==============================================================================
# NITO — THE CENTRAL VALUE (empty / origin / propagating absence)
# ==============================================================================

class NitoType:
    """Singleton empty value. Falsy, prints as 'Nito', and propagates through
    arithmetic (Nito + 5 -> Nito) so missing data never crashes a program."""
    _instance: Optional["NitoType"] = None

    def __new__(cls) -> "NitoType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str: return "Nito"
    def __str__(self) -> str: return "Nito"
    def __bool__(self) -> bool: return False
    def __eq__(self, other: Any) -> bool: return isinstance(other, NitoType)
    def __ne__(self, other: Any) -> bool: return not self.__eq__(other)
    def __hash__(self) -> int: return hash("__Nito__")

Nito = NitoType()

def is_nito(value: Any) -> bool:
    return isinstance(value, NitoType)

# ------------------------------------------------------------------
# Nito as the native unit of value: 1 Nito = 100 Nitters (the fraction).
# Amounts are written `100 nito`, `5 nitters`, `1 nitter` and stored as an
# integer count of Nitters so ledger math is exact (no floating-point drift).
# ------------------------------------------------------------------
NITTERS_PER_NITO = 100

def nitos_render(nitters: int) -> str:
    if nitters % NITTERS_PER_NITO == 0:
        return f"Ñ{nitters // NITTERS_PER_NITO}"
    if -NITTERS_PER_NITO < nitters < NITTERS_PER_NITO:
        return f"{nitters} " + ("Nitter" if abs(nitters) == 1 else "Nitters")
    return f"Ñ{nitters / NITTERS_PER_NITO:.2f}"

class Nitos:
    """A quantity of value denominated in Nito (held as integer Nitters)."""
    __slots__ = ("nitters",)
    def __init__(self, nitters: int): self.nitters = int(nitters)
    @property
    def nito(self) -> float: return self.nitters / NITTERS_PER_NITO
    def __bool__(self) -> bool: return self.nitters != 0
    def __eq__(self, o: Any) -> bool: return isinstance(o, Nitos) and o.nitters == self.nitters
    def __ne__(self, o: Any) -> bool: return not self.__eq__(o)
    def __hash__(self) -> int: return hash(("Nitos", self.nitters))
    def __repr__(self) -> str: return nitos_render(self.nitters)

def is_amount(value: Any) -> bool:
    return isinstance(value, Nitos)

def nito_str(value: Any) -> str:
    """Human-friendly rendering used by `show` and string concatenation."""
    if is_nito(value): return "Nito"
    if isinstance(value, Nitos): return nitos_render(value.nitters)
    if value is True: return "true"
    if value is False: return "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)

# ==============================================================================
# AST NODES
# ==============================================================================

class ASTNode: pass

class ProgramNode(ASTNode):
    def __init__(self, statements: List[ASTNode]): self.statements = statements

class LetNode(ASTNode):
    def __init__(self, name: str, initializer: ASTNode):
        self.name, self.initializer = name, initializer

class AssignNode(ASTNode):
    def __init__(self, name: str, value: ASTNode):
        self.name, self.value = name, value

class BlockDeclNode(ASTNode):
    def __init__(self, name: str, params: List[str], body: "SuiteNode"):
        self.name, self.params, self.body = name, params, body

class ChainDeclNode(ASTNode):
    def __init__(self, name: str, state_fields, transitions):
        self.name = name
        self.state_fields = state_fields      # List[(field_name, init_expr)]
        self.transitions = transitions        # List[BlockDeclNode]

class NewChainNode(ASTNode):
    def __init__(self, name: str): self.name = name

class SuiteNode(ASTNode):
    def __init__(self, statements: List[ASTNode]): self.statements = statements

class IfNode(ASTNode):
    def __init__(self, cond, then_b, elifs, else_b):
        self.condition, self.then_branch = cond, then_b
        self.elif_branches, self.else_branch = elifs, else_b

class WhileNode(ASTNode):
    def __init__(self, cond, body): self.condition, self.body = cond, body

class GiveNode(ASTNode):
    def __init__(self, value: Optional[ASTNode]): self.value = value

class ShowNode(ASTNode):
    def __init__(self, expression: ASTNode): self.expression = expression

class FailNode(ASTNode):
    def __init__(self, expression: ASTNode): self.expression = expression

class UseNode(ASTNode):
    def __init__(self, module: str, name: str): self.module, self.name = module, name

class ExprStmtNode(ASTNode):
    def __init__(self, expression: ASTNode): self.expression = expression

class BinaryOpNode(ASTNode):
    def __init__(self, left, op, right): self.left, self.op, self.right = left, op, right

class UnaryOpNode(ASTNode):
    def __init__(self, op, operand): self.op, self.operand = op, operand

class CallNode(ASTNode):
    def __init__(self, callee, arguments): self.callee, self.arguments = callee, arguments

class GetNode(ASTNode):
    def __init__(self, obj, name): self.obj, self.name = obj, name

class VariableNode(ASTNode):
    def __init__(self, name: str): self.name = name

class LiteralNode(ASTNode):
    def __init__(self, value: Any): self.value = value

# ==============================================================================
# TOKENS & LEXER
# ==============================================================================

class TokenType(Enum):
    LET = auto(); IF = auto(); ELIF = auto(); ELSE = auto(); WHILE = auto()
    BLOCK = auto(); GIVE = auto(); SHOW = auto(); FAIL = auto(); USE = auto()
    CHAIN = auto(); STATE = auto(); NEW = auto()
    AND = auto(); OR = auto(); NOT = auto()
    TRUE = auto(); FALSE = auto(); NITO = auto()
    IDENTIFIER = auto(); NUMBER = auto(); STRING = auto()
    ASSIGN = auto(); PLUS = auto(); MINUS = auto(); STAR = auto(); SLASH = auto(); MODULO = auto()
    EQ = auto(); NEQ = auto(); LT = auto(); GT = auto(); LTE = auto(); GTE = auto()
    PIPE = auto()  # |>
    LPAREN = auto(); RPAREN = auto(); COMMA = auto(); DOT = auto(); COLON = auto()
    NEWLINE = auto(); INDENT = auto(); DEDENT = auto(); EOF = auto()

KEYWORDS = {
    "let": TokenType.LET, "if": TokenType.IF, "elif": TokenType.ELIF,
    "else": TokenType.ELSE, "while": TokenType.WHILE, "block": TokenType.BLOCK,
    "give": TokenType.GIVE, "show": TokenType.SHOW, "fail": TokenType.FAIL,
    "use": TokenType.USE, "and": TokenType.AND, "or": TokenType.OR, "not": TokenType.NOT,
    "chain": TokenType.CHAIN, "state": TokenType.STATE, "new": TokenType.NEW,
    "true": TokenType.TRUE, "false": TokenType.FALSE, "Nito": TokenType.NITO,
}

class Token:
    def __init__(self, ttype, value, line, column):
        self.type, self.value, self.line, self.column = ttype, value, line, column
    def __repr__(self): return f"Token({self.type.name}, {self.value!r}, L{self.line}:C{self.column})"

class NitoSyntaxError(Exception):
    def __init__(self, message: str, line: int, column: int):
        self.line, self.column = line, column
        super().__init__(f"line {line}, column {column}: {message}")

class NitoError(Exception):
    """Raised by `fail` and by runtime faults; carries a beginner-friendly message."""

class Lexer:
    def __init__(self, source: str):
        self.source, self.pos, self.line, self.column = source, 0, 1, 1
        self.length = len(source)
        self.indent_stack = [0]
        self.paren_depth = 0
        self.at_line_start = True

    def peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        return self.source[i] if i < self.length else ""

    def advance(self) -> str:
        ch = self.peek()
        self.pos += 1
        if ch == "\n": self.line += 1; self.column = 1
        else: self.column += 1
        return ch

    def skip_inline(self):
        while self.pos < self.length:
            ch = self.peek()
            if ch in (" ", "\t", "\r"): self.advance()
            elif ch == "#":
                while self.peek() not in ("\n", ""): self.advance()
            else: break

    def read_number(self) -> Token:
        col, num = self.column, ""
        while self.peek().isdigit(): num += self.advance()
        if self.peek() == "." and self.peek(1).isdigit():
            num += self.advance()
            while self.peek().isdigit(): num += self.advance()
        return Token(TokenType.NUMBER, num, self.line, col)

    def read_string(self) -> Token:
        col = self.column
        self.advance()  # opening quote
        out = ""
        while self.pos < self.length:
            ch = self.peek()
            if ch == '"':
                self.advance()
                return Token(TokenType.STRING, out, self.line, col)
            if ch == "\\":
                self.advance()
                esc = self.advance()
                out += {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(esc, "\\" + esc)
            else:
                out += self.advance()
        raise NitoSyntaxError("unterminated string (missing closing quote).", self.line, col)

    def read_word(self) -> Token:
        col, word = self.column, ""
        while self.peek().isalnum() or self.peek() == "_": word += self.advance()
        if word in KEYWORDS: return Token(KEYWORDS[word], word, self.line, col)
        return Token(TokenType.IDENTIFIER, word, self.line, col)

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while self.pos < self.length:
            if self.at_line_start and self.paren_depth == 0:
                spaces = 0
                while self.peek() in (" ", "\t"):
                    spaces += 4 if self.advance() == "\t" else 1
                if self.peek() in ("\n", "\r", "#", ""):
                    self.skip_inline()
                    if self.peek() in ("\n", "\r"): self.advance()
                    if self.pos >= self.length: break
                    continue
                if spaces > self.indent_stack[-1]:
                    self.indent_stack.append(spaces)
                    tokens.append(Token(TokenType.INDENT, "", self.line, 1))
                while spaces < self.indent_stack[-1]:
                    self.indent_stack.pop()
                    tokens.append(Token(TokenType.DEDENT, "", self.line, 1))
                if spaces != self.indent_stack[-1]:
                    raise NitoSyntaxError("inconsistent indentation.", self.line, 1)
                self.at_line_start = False

            self.skip_inline()
            if self.pos >= self.length: break
            ch, line, col = self.peek(), self.line, self.column

            if ch in ("\n", "\r"):
                self.advance()
                if self.paren_depth == 0:
                    if tokens and tokens[-1].type not in (TokenType.NEWLINE, TokenType.INDENT, TokenType.DEDENT):
                        tokens.append(Token(TokenType.NEWLINE, "\n", line, col))
                    self.at_line_start = True
                continue
            if ch.isdigit(): tokens.append(self.read_number()); continue
            if ch.isalpha() or ch == "_": tokens.append(self.read_word()); continue
            if ch == '"': tokens.append(self.read_string()); continue

            two = ch + self.peek(1)
            simple2 = {"==": TokenType.EQ, "!=": TokenType.NEQ, "<=": TokenType.LTE,
                       ">=": TokenType.GTE, "|>": TokenType.PIPE}
            if two in simple2:
                self.advance(); self.advance()
                tokens.append(Token(simple2[two], two, line, col)); continue

            simple1 = {"=": TokenType.ASSIGN, "+": TokenType.PLUS, "-": TokenType.MINUS,
                       "*": TokenType.STAR, "/": TokenType.SLASH, "%": TokenType.MODULO,
                       "<": TokenType.LT, ">": TokenType.GT, ",": TokenType.COMMA,
                       ".": TokenType.DOT, ":": TokenType.COLON}
            if ch in simple1:
                self.advance()
                tokens.append(Token(simple1[ch], ch, line, col)); continue
            if ch == "(":
                self.advance(); self.paren_depth += 1
                tokens.append(Token(TokenType.LPAREN, "(", line, col)); continue
            if ch == ")":
                self.advance(); self.paren_depth = max(0, self.paren_depth - 1)
                tokens.append(Token(TokenType.RPAREN, ")", line, col)); continue
            raise NitoSyntaxError(f"unexpected character {ch!r}.", line, col)

        while len(self.indent_stack) > 1:
            self.indent_stack.pop(); tokens.append(Token(TokenType.DEDENT, "", self.line, self.column))
        if tokens and tokens[-1].type not in (TokenType.NEWLINE, TokenType.DEDENT):
            tokens.append(Token(TokenType.NEWLINE, "\n", self.line, self.column))
        tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        return tokens

# ==============================================================================
# PARSER (recursive descent; clear errors, no auto-healing)
# ==============================================================================

class Parser:
    def __init__(self, tokens: List[Token]): self.tokens, self.current = tokens, 0
    def peek(self) -> Token: return self.tokens[self.current]
    def previous(self) -> Token: return self.tokens[self.current - 1]
    def is_at_end(self) -> bool: return self.peek().type == TokenType.EOF
    def check(self, t) -> bool: return not self.is_at_end() and self.peek().type == t
    def advance(self) -> Token:
        if not self.is_at_end(): self.current += 1
        return self.previous()
    def match(self, *types) -> bool:
        for t in types:
            if self.check(t): self.advance(); return True
        return False
    def consume(self, t, msg) -> Token:
        if self.check(t): return self.advance()
        tok = self.peek()
        raise NitoSyntaxError(f"{msg} (found {tok.value!r}).", tok.line, tok.column)

    def parse(self) -> ProgramNode:
        statements = []
        while not self.is_at_end():
            if self.match(TokenType.NEWLINE): continue
            statements.append(self.statement())
        return ProgramNode(statements)

    def end_statement(self):
        if not (self.match(TokenType.NEWLINE) or self.check(TokenType.DEDENT) or self.is_at_end()):
            tok = self.peek()
            raise NitoSyntaxError(f"expected end of line (found {tok.value!r}).", tok.line, tok.column)

    def statement(self) -> ASTNode:
        if self.match(TokenType.LET): return self.let_statement()
        if self.match(TokenType.BLOCK): return self.block_declaration()
        if self.match(TokenType.CHAIN): return self.chain_declaration()
        if self.match(TokenType.IF): return self.if_statement()
        if self.match(TokenType.WHILE): return self.while_statement()
        if self.match(TokenType.GIVE): return self.give_statement()
        if self.match(TokenType.SHOW): return self.show_statement()
        if self.match(TokenType.FAIL): return self.fail_statement()
        if self.match(TokenType.USE): return self.use_statement()
        expr = self.expression()
        self.end_statement()
        return ExprStmtNode(expr)

    def let_statement(self) -> ASTNode:
        name = self.consume(TokenType.IDENTIFIER, "expected a name after 'let'").value
        self.consume(TokenType.ASSIGN, "expected '=' after the name in a 'let'")
        value = self.expression()
        self.end_statement()
        return LetNode(name, value)

    def block_declaration(self) -> ASTNode:
        name = self.consume(TokenType.IDENTIFIER, "expected a block name after 'block'").value
        self.consume(TokenType.LPAREN, "expected '(' after the block name")
        params = []
        if not self.check(TokenType.RPAREN):
            while True:
                params.append(self.consume(TokenType.IDENTIFIER, "expected a parameter name").value)
                if not self.match(TokenType.COMMA): break
        self.consume(TokenType.RPAREN, "expected ')' to close the parameter list")
        body = self.suite("block")
        return BlockDeclNode(name, params, body)

    def chain_declaration(self) -> ASTNode:
        name = self.consume(TokenType.IDENTIFIER, "expected a chain name after 'chain'").value
        self.consume(TokenType.COLON, "expected ':' after the chain name")
        self.consume(TokenType.NEWLINE, "expected a new line after 'chain ...:'")
        self.consume(TokenType.INDENT, "expected an indented body for the chain")
        state_fields, transitions = [], []
        while not self.check(TokenType.DEDENT) and not self.is_at_end():
            if self.match(TokenType.NEWLINE): continue
            if self.match(TokenType.STATE):
                state_fields = self.state_block()
            elif self.match(TokenType.BLOCK):
                transitions.append(self.block_declaration())
            else:
                tok = self.peek()
                raise NitoSyntaxError(f"inside a chain, expected 'state' or 'block' (found {tok.value!r}).", tok.line, tok.column)
        self.consume(TokenType.DEDENT, "expected the chain body to end")
        if not state_fields:
            raise NitoSyntaxError(f"chain '{name}' needs a 'state:' block.", self.previous().line, 1)
        return ChainDeclNode(name, state_fields, transitions)

    def state_block(self):
        self.consume(TokenType.COLON, "expected ':' after 'state'")
        self.consume(TokenType.NEWLINE, "expected a new line after 'state:'")
        self.consume(TokenType.INDENT, "expected indented fields under 'state:'")
        fields = []
        while not self.check(TokenType.DEDENT) and not self.is_at_end():
            if self.match(TokenType.NEWLINE): continue
            fname = self.consume(TokenType.IDENTIFIER, "expected a state field name").value
            self.consume(TokenType.ASSIGN, "expected '=' after the field name")
            fields.append((fname, self.expression()))
            self.end_statement()
        self.consume(TokenType.DEDENT, "expected the 'state:' block to end")
        return fields

    def if_statement(self) -> ASTNode:
        cond = self.expression()
        then_b = self.suite("if")
        elifs, else_b = [], None
        while self.match(TokenType.ELIF):
            ec = self.expression()
            elifs.append((ec, self.suite("elif")))
        if self.match(TokenType.ELSE):
            else_b = self.suite("else")
        return IfNode(cond, then_b, elifs, else_b)

    def while_statement(self) -> ASTNode:
        cond = self.expression()
        return WhileNode(cond, self.suite("while"))

    def give_statement(self) -> ASTNode:
        value = None
        if not (self.check(TokenType.NEWLINE) or self.check(TokenType.DEDENT) or self.is_at_end()):
            value = self.expression()
        self.end_statement()
        return GiveNode(value)

    def show_statement(self) -> ASTNode:
        expr = self.expression(); self.end_statement(); return ShowNode(expr)

    def fail_statement(self) -> ASTNode:
        expr = self.expression(); self.end_statement(); return FailNode(expr)

    def use_statement(self) -> ASTNode:
        parts = [self.consume(TokenType.IDENTIFIER, "expected a module or function name after 'use'").value]
        while self.match(TokenType.DOT):
            parts.append(self.consume(TokenType.IDENTIFIER, "expected a name after '.'").value)
        self.end_statement()
        if len(parts) > 1: return UseNode(".".join(parts[:-1]), parts[-1])
        return UseNode("", parts[0])

    def suite(self, keyword: str) -> SuiteNode:
        self.consume(TokenType.COLON, f"expected ':' after the '{keyword}' header")
        if self.match(TokenType.NEWLINE):
            self.consume(TokenType.INDENT, f"expected an indented body for '{keyword}'")
            statements = []
            while not self.check(TokenType.DEDENT) and not self.is_at_end():
                if self.match(TokenType.NEWLINE): continue
                statements.append(self.statement())
            self.consume(TokenType.DEDENT, f"expected the '{keyword}' body to end")
            return SuiteNode(statements)
        return SuiteNode([self.statement()])  # inline single-statement form

    # --- expressions ---
    def expression(self) -> ASTNode: return self.assignment()

    def assignment(self) -> ASTNode:
        expr = self.pipe()
        if self.match(TokenType.ASSIGN):
            tok = self.previous()
            value = self.assignment()
            if isinstance(expr, VariableNode): return AssignNode(expr.name, value)
            raise NitoSyntaxError("you can only assign to a name.", tok.line, tok.column)
        return expr

    def pipe(self) -> ASTNode:
        expr = self.logical_or()
        while self.match(TokenType.PIPE):
            right = self.logical_or()
            if isinstance(right, CallNode):
                expr = CallNode(right.callee, [expr] + right.arguments)
            else:
                expr = CallNode(right, [expr])
        return expr

    def logical_or(self) -> ASTNode:
        expr = self.logical_and()
        while self.match(TokenType.OR):
            expr = BinaryOpNode(expr, "or", self.logical_and())
        return expr

    def logical_and(self) -> ASTNode:
        expr = self.equality()
        while self.match(TokenType.AND):
            expr = BinaryOpNode(expr, "and", self.equality())
        return expr

    def equality(self) -> ASTNode:
        expr = self.comparison()
        while self.match(TokenType.EQ, TokenType.NEQ):
            expr = BinaryOpNode(expr, self.previous().value, self.comparison())
        return expr

    def comparison(self) -> ASTNode:
        expr = self.addition()
        while self.match(TokenType.LT, TokenType.GT, TokenType.LTE, TokenType.GTE):
            expr = BinaryOpNode(expr, self.previous().value, self.addition())
        return expr

    def addition(self) -> ASTNode:
        expr = self.multiplication()
        while self.match(TokenType.PLUS, TokenType.MINUS):
            expr = BinaryOpNode(expr, self.previous().value, self.multiplication())
        return expr

    def multiplication(self) -> ASTNode:
        expr = self.unary()
        while self.match(TokenType.STAR, TokenType.SLASH, TokenType.MODULO):
            expr = BinaryOpNode(expr, self.previous().value, self.unary())
        return expr

    def unary(self) -> ASTNode:
        if self.match(TokenType.NOT, TokenType.MINUS):
            return UnaryOpNode(self.previous().value, self.unary())
        return self.call()

    def call(self) -> ASTNode:
        expr = self.primary()
        while True:
            if self.match(TokenType.LPAREN):
                args = []
                if not self.check(TokenType.RPAREN):
                    while True:
                        args.append(self.expression())
                        if not self.match(TokenType.COMMA): break
                self.consume(TokenType.RPAREN, "expected ')' after arguments")
                expr = CallNode(expr, args)
            elif self.match(TokenType.DOT):
                name = self.consume(TokenType.IDENTIFIER, "expected a property name after '.'").value
                expr = GetNode(expr, name)
            else:
                break
        return expr

    def primary(self) -> ASTNode:
        if self.match(TokenType.NEW):
            name = self.consume(TokenType.IDENTIFIER, "expected a chain name after 'new'").value
            self.consume(TokenType.LPAREN, "expected '(' after the chain name")
            self.consume(TokenType.RPAREN, "expected ')' (chains take no constructor arguments yet)")
            return NewChainNode(name)
        if self.match(TokenType.TRUE): return LiteralNode(True)
        if self.match(TokenType.FALSE): return LiteralNode(False)
        if self.match(TokenType.NITO): return LiteralNode(Nito)
        if self.match(TokenType.NUMBER):
            v = self.previous().value
            num = float(v) if "." in v else int(v)
            if self.check(TokenType.IDENTIFIER) and self.peek().value in ("nito", "nitter", "nitters"):
                unit = self.advance().value
                nitters = round(num * NITTERS_PER_NITO) if unit == "nito" else round(num)
                return LiteralNode(Nitos(nitters))
            return LiteralNode(num)
        if self.match(TokenType.STRING): return LiteralNode(self.previous().value)
        if self.match(TokenType.IDENTIFIER): return VariableNode(self.previous().value)
        if self.match(TokenType.LPAREN):
            expr = self.expression()
            self.consume(TokenType.RPAREN, "expected ')' after the expression")
            return expr
        tok = self.peek()
        raise NitoSyntaxError(f"expected a value or expression (found {tok.value!r}).", tok.line, tok.column)

# ==============================================================================
# SEMANTICS — Nito-aware operators
# ==============================================================================

def _nitos_op(left: Any, op: str, right: Any) -> Any:
    both = is_amount(left) and is_amount(right)
    if op in ("+", "-"):
        if not both:
            raise NitoError("both sides must be Nito amounts (write e.g. '5 nito').")
        n = left.nitters + right.nitters if op == "+" else left.nitters - right.nitters
        return Nitos(n)
    if op in ("<", ">", "<=", ">="):
        if not both:
            raise NitoError("you can only compare Nito amounts with Nito amounts.")
        a, b = left.nitters, right.nitters
        return {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
    if op == "*":
        amount, scalar = (left, right) if is_amount(left) else (right, left)
        if isinstance(scalar, (int, float)):
            return Nitos(round(amount.nitters * scalar))
        raise NitoError("a Nito amount can only be scaled by a plain number.")
    raise NitoError(f"operator '{op}' is not defined for Nito amounts.")

def evaluate_binary_op(left: Any, op: str, right: Any) -> Any:
    if op == "or": return left if bool(left) else right
    if op == "and": return right if bool(left) else left
    if op == "==": return left == right
    if op == "!=": return left != right

    # Nito propagation: absence flows through arithmetic and ordering.
    if is_nito(left) or is_nito(right):
        return Nito

    # String concatenation renders any operand (incl. Nito amounts) nicely.
    if op == "+" and (isinstance(left, str) or isinstance(right, str)):
        return nito_str(left) + nito_str(right)

    # Value arithmetic in Nito (the ledger's unit of account).
    if is_amount(left) or is_amount(right):
        return _nitos_op(left, op, right)

    if op == "<": return left < right
    if op == ">": return left > right
    if op == "<=": return left <= right
    if op == ">=": return left >= right
    if op == "+":
        if isinstance(left, str) or isinstance(right, str):
            return nito_str(left) + nito_str(right)
        return left + right
    if op == "-": return left - right
    if op == "*": return left * right
    if op == "/":
        if right == 0: raise NitoError("you can't divide by zero.")
        return left / right
    if op == "%":
        if right == 0: raise NitoError("you can't take a remainder by zero.")
        return left % right
    raise NitoError(f"unknown operator '{op}'.")

# ==============================================================================
# SCOPES & FUNCTIONS
# ==============================================================================

class Environment:
    def __init__(self, parent: Optional["Environment"] = None):
        self.values: Dict[str, Any] = {}
        self.parent = parent

    def define(self, name: str, value: Any):
        self.values[name] = value

    def assign(self, name: str, value: Any):
        env = self
        while env is not None:
            if name in env.values:
                env.values[name] = value
                return
            env = env.parent
        raise NitoError(f"unknown name '{name}' (declare it first with 'let').")

    def get(self, name: str) -> Any:
        env = self
        while env is not None:
            if name in env.values:
                return env.values[name]
            env = env.parent
        raise NitoError(f"unknown name '{name}' (declare it first with 'let').")

class NitoNativeFunction:
    def __init__(self, name, func): self.name, self.func = name, func
    def call(self, args): return self.func(*args)
    def __repr__(self): return f"<native {self.name}>"

class NitoBlock:
    """A user-defined block (function): deterministic input -> output."""
    def __init__(self, name, params, bytecode, closure):
        self.name, self.params, self.bytecode, self.closure = name, params, bytecode, closure
    def call(self, executor, args):
        if len(args) != len(self.params):
            raise NitoError(f"block '{self.name}' expects {len(self.params)} argument(s), got {len(args)}.")
        env = Environment(self.closure)
        for p, v in zip(self.params, args):
            env.define(p, v)
        sub = NitoSupremeExecutor(self.bytecode, env)
        while sub.step():
            pass
        return sub.stack.pop() if sub.stack else Nito
    def __repr__(self): return f"<block {self.name}>"

# ==============================================================================
# STATE CHAINS — deterministic, hash-linked, verifiable by replay
# ==============================================================================
# A chain transition must be deterministic for verify-by-replay to be sound, so
# while one is running we forbid calling external (FFI) functions. This counter
# tracks transition depth across nested block calls (single-threaded execution).
_TRANSITION_DEPTH = 0

def _canonical(value: Any) -> str:
    """Unambiguous, deterministic serialization used for state roots."""
    if is_nito(value): return "N"
    if isinstance(value, Nitos): return "n" + str(value.nitters)
    if value is True: return "T"
    if value is False: return "F"
    if isinstance(value, bool): return "T" if value else "F"
    if isinstance(value, int): return "i" + str(value)
    if isinstance(value, float): return "f" + repr(value)
    if isinstance(value, str): return "s" + str(len(value)) + ":" + value
    if isinstance(value, (list, tuple)): return "[" + ",".join(_canonical(v) for v in value) + "]"
    if isinstance(value, dict): return "{" + ",".join(k + "=" + _canonical(value[k]) for k in sorted(value)) + "}"
    return "?" + repr(value)

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def genesis_root(state: Dict[str, Any]) -> str:
    return _sha("GENESIS::" + _canonical(state))

def next_root(prev: str, name: str, args: list, state: Dict[str, Any]) -> str:
    return _sha(prev + "::" + name + "::" + _canonical(args) + "::" + _canonical(state))

class ChainTemplate:
    """The declared shape of a chain: initial state + transition blocks."""
    def __init__(self, name, state_inits, transitions, def_env):
        self.name = name
        self.state_inits = state_inits        # List[(field, Bytecode)]
        self.transitions = transitions        # Dict[name -> (params, Bytecode)]
        self.def_env = def_env

    def instantiate(self) -> "ChainInstance":
        state: Dict[str, Any] = {}
        for field, code in self.state_inits:
            vm = NitoSupremeExecutor(code, Environment(self.def_env))
            while vm.step():
                pass
            state[field] = vm.stack[-1] if vm.stack else Nito
        return ChainInstance(self, state)

    def run_transition(self, state: Dict[str, Any], name: str, args: list) -> Dict[str, Any]:
        """Apply a transition to a copy of `state`, returning the new state.
        Raises NitoError on failure (caller decides whether to commit)."""
        global _TRANSITION_DEPTH
        if name not in self.transitions:
            raise NitoError(f"chain '{self.name}' has no action '{name}'.")
        params, code = self.transitions[name]
        if len(args) != len(params):
            raise NitoError(f"action '{name}' expects {len(params)} argument(s), got {len(args)}.")
        env = Environment(self.def_env)
        for k, v in state.items():
            env.define(k, v)
        for p, a in zip(params, args):
            env.define(p, a)
        vm = NitoSupremeExecutor(code, env)
        _TRANSITION_DEPTH += 1
        try:
            while vm.step():
                pass
        finally:
            _TRANSITION_DEPTH -= 1
        return {k: env.get(k) for k in state}

class ChainInstance:
    """A live chain: current state plus a hash-linked, replayable history."""
    def __init__(self, template: ChainTemplate, state: Dict[str, Any]):
        self.template = template
        self.genesis_state = dict(state)
        self.state = dict(state)
        self.history: List = []               # List[(name, args, root)]
        self.root = genesis_root(state)

    def apply_transition(self, name: str, args: list) -> Any:
        new_state = self.template.run_transition(self.state, name, args)  # raises -> abort, state intact
        self.state = new_state
        self.root = next_root(self.root, name, args, new_state)
        self.history.append((name, list(args), self.root))
        return Nito

    def _replay(self):
        """Re-execute the whole history from genesis. Returns (final_state,
        final_root, links_ok) where links_ok is False if any recorded root
        doesn't match the recomputation."""
        state = dict(self.genesis_state)
        root = genesis_root(state)
        links_ok = True
        with redirect_stdout(io.StringIO()):  # transitions may `show`; stay quiet on replay
            for name, args, recorded in self.history:
                state = self.template.run_transition(state, name, list(args))
                root = next_root(root, name, args, state)
                if root != recorded:
                    links_ok = False
        return state, root, links_ok

    def verify(self) -> bool:
        """A single validator re-runs the chain and checks every hash-link AND
        that the live state matches the replay. Tampering with any past
        transition, recorded root, or the current state breaks verification."""
        try:
            state, root, links_ok = self._replay()
        except NitoError:
            return False
        return links_ok and root == self.root and state == self.state

    def replay(self) -> str:
        """Deterministically rebuild the head root from history."""
        _, root, _ = self._replay()
        return root

    def get_property(self, name: str) -> Any:
        if name in self.state:
            return self.state[name]
        if name in self.template.transitions:
            return NitoNativeFunction(name, lambda *a, _n=name: self.apply_transition(_n, list(a)))
        if name == "root":
            return self.root
        if name == "history":
            return [f"{n}({', '.join(nito_str(x) for x in a)})" for (n, a, _) in self.history]
        if name == "verify":
            return NitoNativeFunction("verify", lambda *a: self.verify())
        if name == "replay":
            return NitoNativeFunction("replay", lambda *a: self.replay())
        return Nito

    def __repr__(self): return f"<chain {self.template.name} root={self.root[:8]}…>"

# ==============================================================================
# BYTECODE
# ==============================================================================

class Opcode(Enum):
    LOAD_CONST = auto(); LOAD_NAME = auto(); STORE_NAME = auto(); DECLARE_NAME = auto()
    ADD = auto(); SUB = auto(); MUL = auto(); DIV = auto(); MOD = auto(); COMPARE = auto()
    NEGATE = auto(); NOT = auto()
    JUMP_IF_FALSE = auto(); JUMP = auto(); CALL = auto(); RETURN_VALUE = auto()
    SHOW = auto(); FAIL = auto(); IMPORT_FFI = auto(); POP_TOP = auto(); GET_PROPERTY = auto()
    NEW_CHAIN = auto()

class Instruction:
    def __init__(self, opcode, arg=None): self.opcode, self.arg = opcode, arg
    def __repr__(self): return f"Instruction({self.opcode.name}, {self.arg})"

class Bytecode:
    def __init__(self):
        self.instructions: List[Instruction] = []
        self.constants: List[Any] = []
        self.names: List[str] = []
    def add_const(self, val) -> int:
        for i, c in enumerate(self.constants):
            if c is val: return i
            if type(c) is type(val) and not callable(c) and c == val: return i
        self.constants.append(val); return len(self.constants) - 1
    def add_name(self, name) -> int:
        if name in self.names: return self.names.index(name)
        self.names.append(name); return len(self.names) - 1
    def emit(self, opcode, arg=None) -> int:
        self.instructions.append(Instruction(opcode, arg)); return len(self.instructions) - 1

# ==============================================================================
# COMPILER
# ==============================================================================

class Compiler:
    def __init__(self): self.code = Bytecode()

    def compile(self, node: ASTNode):
        method = getattr(self, "_c_" + type(node).__name__, None)
        if method is None:
            raise NitoError(f"internal: cannot compile {type(node).__name__}")
        method(node)

    def _c_ProgramNode(self, n):
        for s in n.statements: self.compile(s)
    def _c_SuiteNode(self, n):
        for s in n.statements: self.compile(s)
    def _c_LetNode(self, n):
        self.compile(n.initializer)
        self.code.emit(Opcode.DECLARE_NAME, self.code.add_name(n.name))
    def _c_AssignNode(self, n):
        self.compile(n.value)
        self.code.emit(Opcode.STORE_NAME, self.code.add_name(n.name))
    def _c_LiteralNode(self, n):
        self.code.emit(Opcode.LOAD_CONST, self.code.add_const(n.value))
    def _c_VariableNode(self, n):
        self.code.emit(Opcode.LOAD_NAME, self.code.add_name(n.name))
    def _c_BinaryOpNode(self, n):
        self.compile(n.left); self.compile(n.right)
        ops = {"+": Opcode.ADD, "-": Opcode.SUB, "*": Opcode.MUL, "/": Opcode.DIV, "%": Opcode.MOD}
        if n.op in ops: self.code.emit(ops[n.op])
        else: self.code.emit(Opcode.COMPARE, n.op)
    def _c_UnaryOpNode(self, n):
        self.compile(n.operand)
        self.code.emit(Opcode.NOT if n.op == "not" else Opcode.NEGATE)
    def _c_GetNode(self, n):
        self.compile(n.obj)
        self.code.emit(Opcode.GET_PROPERTY, self.code.add_name(n.name))
    def _c_ShowNode(self, n):
        self.compile(n.expression); self.code.emit(Opcode.SHOW)
    def _c_FailNode(self, n):
        self.compile(n.expression); self.code.emit(Opcode.FAIL)
    def _c_UseNode(self, n):
        self.code.emit(Opcode.IMPORT_FFI, (self.code.add_name(n.name), self.code.add_const(n.module)))
    def _c_ExprStmtNode(self, n):
        self.compile(n.expression); self.code.emit(Opcode.POP_TOP)
    def _c_IfNode(self, n):
        exit_jumps = []
        self.compile(n.condition)
        jnext = self.code.emit(Opcode.JUMP_IF_FALSE, 0)
        self.compile(n.then_branch)
        if n.elif_branches or n.else_branch:
            exit_jumps.append(self.code.emit(Opcode.JUMP, 0))
        self.code.instructions[jnext].arg = len(self.code.instructions)
        for cond, body in n.elif_branches:
            self.compile(cond)
            jnext = self.code.emit(Opcode.JUMP_IF_FALSE, 0)
            self.compile(body)
            exit_jumps.append(self.code.emit(Opcode.JUMP, 0))
            self.code.instructions[jnext].arg = len(self.code.instructions)
        if n.else_branch: self.compile(n.else_branch)
        end = len(self.code.instructions)
        for j in exit_jumps: self.code.instructions[j].arg = end
    def _c_WhileNode(self, n):
        start = len(self.code.instructions)
        self.compile(n.condition)
        jfalse = self.code.emit(Opcode.JUMP_IF_FALSE, 0)
        self.compile(n.body)
        self.code.emit(Opcode.JUMP, start)
        self.code.instructions[jfalse].arg = len(self.code.instructions)
    def _c_BlockDeclNode(self, n):
        fn_comp = Compiler()
        fn_comp.compile(n.body)
        fn_comp.code.emit(Opcode.LOAD_CONST, fn_comp.code.add_const(Nito))
        fn_comp.code.emit(Opcode.RETURN_VALUE)
        block = NitoBlock(n.name, n.params, fn_comp.code, None)
        self.code.emit(Opcode.LOAD_CONST, self.code.add_const(block))
        self.code.emit(Opcode.DECLARE_NAME, self.code.add_name(n.name))
    def _c_CallNode(self, n):
        self.compile(n.callee)
        for a in n.arguments: self.compile(a)
        self.code.emit(Opcode.CALL, len(n.arguments))
    def _c_GiveNode(self, n):
        if n.value: self.compile(n.value)
        else: self.code.emit(Opcode.LOAD_CONST, self.code.add_const(Nito))
        self.code.emit(Opcode.RETURN_VALUE)
    def _c_ChainDeclNode(self, n):
        state_inits = []
        for field, expr in n.state_fields:
            c = Compiler(); c.compile(expr)
            state_inits.append((field, c.code))
        transitions = {}
        for bd in n.transitions:
            c = Compiler(); c.compile(bd.body)
            transitions[bd.name] = (bd.params, c.code)
        tmpl = ChainTemplate(n.name, state_inits, transitions, None)
        self.code.emit(Opcode.LOAD_CONST, self.code.add_const(tmpl))
        self.code.emit(Opcode.DECLARE_NAME, self.code.add_name(n.name))
    def _c_NewChainNode(self, n):
        self.code.emit(Opcode.LOAD_NAME, self.code.add_name(n.name))
        self.code.emit(Opcode.NEW_CHAIN)

# ==============================================================================
# NITOSUPREMEEXECUTOR — the Verifiable State-Transition Executor (deterministic VM)
# ==============================================================================

class NitoSupremeExecutor:
    """Deterministic stack machine. Determinism is the property that will let a
    single server validate State Chains by replay (verify-by-replay, later phase)."""
    def __init__(self, code: Bytecode, environment: Optional[Environment] = None):
        self.code = code
        self.ip = 0
        self.stack: List[Any] = []
        self.environment = environment if environment else Environment()

    def step(self) -> bool:
        if self.ip >= len(self.code.instructions): return False
        instr = self.code.instructions[self.ip]
        self.ip += 1
        self.execute(instr)
        return True

    def pop(self) -> Any:
        if not self.stack: raise NitoError("internal: stack underflow.")
        return self.stack.pop()

    def execute(self, instr: Instruction):
        op, arg = instr.opcode, instr.arg
        if op == Opcode.LOAD_CONST:
            val = self.code.constants[arg]
            if isinstance(val, NitoBlock):
                val = NitoBlock(val.name, val.params, val.bytecode, self.environment)
            elif isinstance(val, ChainTemplate):
                val = ChainTemplate(val.name, val.state_inits, val.transitions, self.environment)
            self.stack.append(val)
        elif op == Opcode.LOAD_NAME:
            self.stack.append(self.environment.get(self.code.names[arg]))
        elif op == Opcode.STORE_NAME:
            val = self.pop()
            self.environment.assign(self.code.names[arg], val)
            self.stack.append(val)  # assignment is an expression
        elif op == Opcode.DECLARE_NAME:
            self.environment.define(self.code.names[arg], self.pop())
        elif op == Opcode.ADD:
            r = self.pop(); l = self.pop(); self.stack.append(evaluate_binary_op(l, "+", r))
        elif op == Opcode.SUB:
            r = self.pop(); l = self.pop(); self.stack.append(evaluate_binary_op(l, "-", r))
        elif op == Opcode.MUL:
            r = self.pop(); l = self.pop(); self.stack.append(evaluate_binary_op(l, "*", r))
        elif op == Opcode.DIV:
            r = self.pop(); l = self.pop(); self.stack.append(evaluate_binary_op(l, "/", r))
        elif op == Opcode.MOD:
            r = self.pop(); l = self.pop(); self.stack.append(evaluate_binary_op(l, "%", r))
        elif op == Opcode.COMPARE:
            r = self.pop(); l = self.pop(); self.stack.append(evaluate_binary_op(l, arg, r))
        elif op == Opcode.NEGATE:
            self.stack.append(evaluate_binary_op(0, "-", self.pop()))
        elif op == Opcode.NOT:
            self.stack.append(not bool(self.pop()))
        elif op == Opcode.JUMP:
            self.ip = arg
        elif op == Opcode.JUMP_IF_FALSE:
            if not bool(self.pop()): self.ip = arg
        elif op == Opcode.SHOW:
            print(nito_str(self.pop()))
        elif op == Opcode.FAIL:
            raise NitoError(nito_str(self.pop()))
        elif op == Opcode.CALL:
            args = [self.pop() for _ in range(arg)][::-1]
            callee = self.pop()
            if isinstance(callee, NitoNativeFunction):
                if _TRANSITION_DEPTH > 0:
                    raise NitoError(f"a chain transition must stay deterministic; it can't call the external function '{callee.name}'.")
                self.stack.append(callee.call(args))
            elif isinstance(callee, NitoBlock):
                self.stack.append(callee.call(self, args))
            else:
                raise NitoError(f"'{nito_str(callee)}' is not a block you can call.")
        elif op == Opcode.NEW_CHAIN:
            tmpl = self.pop()
            if not isinstance(tmpl, ChainTemplate):
                raise NitoError(f"'{nito_str(tmpl)}' is not a chain you can create with 'new'.")
            self.stack.append(tmpl.instantiate())
        elif op == Opcode.RETURN_VALUE:
            self.ip = len(self.code.instructions)
        elif op == Opcode.POP_TOP:
            self.pop()
        elif op == Opcode.GET_PROPERTY:
            name = self.code.names[arg]
            obj = self.pop()
            self.stack.append(self._get_property(obj, name))
        elif op == Opcode.IMPORT_FFI:
            self._import_ffi(arg)
        else:
            raise NitoError(f"internal: unknown opcode {op.name}")

    def _get_property(self, obj, name):
        # Nito-safe navigation: missing data yields Nito instead of crashing.
        if is_nito(obj): return Nito
        if isinstance(obj, ChainInstance): return obj.get_property(name)
        if name.startswith("__"): return Nito
        if isinstance(obj, dict): return obj[name] if name in obj else Nito
        try: return getattr(obj, name)
        except AttributeError: return Nito

    def _import_ffi(self, arg):
        name = self.code.names[arg[0]]
        module = self.code.constants[arg[1]]
        if module:
            if module not in ALLOWED_FFI_MODULES:
                raise NitoError(f"'use' of module '{module}' is not allowed (allowed: {sorted(ALLOWED_FFI_MODULES)}).")
            func = getattr(__import__(module, fromlist=[name]), name, None)
        else:
            if name not in ALLOWED_FFI_BUILTINS:
                raise NitoError(f"'use' of '{name}' is not allowed.")
            import builtins
            func = getattr(builtins, name, None)
        if not callable(func):
            raise NitoError(f"'use' target '{name}' was not found or is not callable.")
        self.environment.define(name, NitoNativeFunction(name, func))

# ==============================================================================
# RUNNER, REPL & CLI
# ==============================================================================

class Interpreter:
    def __init__(self):
        self.global_env = Environment()

    def run(self, source: str) -> Any:
        tokens = Lexer(source).tokenize()
        ast = Parser(tokens).parse()
        compiler = Compiler()
        compiler.compile(ast)
        compiler.code.emit(Opcode.RETURN_VALUE)
        vm = NitoSupremeExecutor(compiler.code, self.global_env)
        while vm.step():
            pass
        return vm.stack[-1] if vm.stack else Nito

def run_code(source: str, interpreter: Optional[Interpreter] = None) -> Any:
    """Run NitoScript source. Errors surface honestly — there is no silent healing."""
    return (interpreter or Interpreter()).run(source)

def start_repl():
    print(f"NitoScript v{__version__} — type 'exit' to leave.")
    interp = Interpreter()
    while True:
        try:
            line = input("nito> ")
        except (KeyboardInterrupt, EOFError):
            print("\nbye."); break
        if line.strip() in ("exit", "quit"): break
        if not line.strip(): continue
        try:
            run_code(line, interp)
        except (NitoError, NitoSyntaxError) as e:
            print(f"[Error] {e}", file=sys.stderr)

def main():
    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1], "r", encoding="utf-8") as f:
                source = f.read()
        except FileNotFoundError:
            print(f"[Error] file not found: '{sys.argv[1]}'", file=sys.stderr); sys.exit(1)
        try:
            run_code(source)
        except (NitoError, NitoSyntaxError) as e:
            print(f"[Error] {e}", file=sys.stderr); sys.exit(1)
        except MemoryError:
            print("[Error] out of memory — the program tried to allocate too much.", file=sys.stderr); sys.exit(1)
        except RecursionError:
            print("[Error] too much recursion.", file=sys.stderr); sys.exit(1)
    else:
        start_repl()

if __name__ == "__main__":
    main()
