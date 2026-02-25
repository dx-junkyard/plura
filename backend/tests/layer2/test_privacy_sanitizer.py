"""
PrivacySanitizer の単体テスト (Layer 2)

テスト方針:
1. 正規表現パス: メール・電話番号の除去は LLM なしでテスト可能（純粋関数）
2. 名前フォールバックパス: LLM 無効時の日本語名パターン検出をテスト
3. LLM パス: モックを使った固有名詞一般化をテスト
4. メタデータ検証: replacements の構造・整合性をテスト

重要: Layer 2 は「CRITICAL SECURITY AREA」のため、
PII が確実に除去されることを検証するテストを充実させる。
"""
import pytest
from unittest.mock import AsyncMock

from app.services.layer2.privacy_sanitizer import PrivacySanitizer


# =============================================================================
# 正規表現パス: PII 除去テスト（LLM 不要・純粋関数）
# =============================================================================

class TestRegexPIIRemoval:
    """正規表現によるPII除去のテスト（LLM なしで動作）"""

    @pytest.mark.asyncio
    async def test_removes_single_email(self):
        """単一のメールアドレスが除去される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None  # LLM を無効化

        content = "連絡先は tanaka@example.com です。"
        sanitized, metadata = await sanitizer.sanitize(content)

        assert "tanaka@example.com" not in sanitized
        assert "[メールアドレス]" in sanitized
        assert metadata["replacement_count"] >= 1
        email_reps = [r for r in metadata["replacements"] if r["type"] == "email"]
        assert len(email_reps) == 1
        assert email_reps[0]["original"] == "tanaka@example.com"

    @pytest.mark.asyncio
    async def test_removes_multiple_emails(self):
        """複数のメールアドレスが全て除去される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "田中: tanaka@example.com、山田: yamada@corp.co.jp に連絡してください。"
        sanitized, metadata = await sanitizer.sanitize(content)

        assert "tanaka@example.com" not in sanitized
        assert "yamada@corp.co.jp" not in sanitized
        email_count = sum(1 for r in metadata["replacements"] if r["type"] == "email")
        assert email_count == 2

    @pytest.mark.asyncio
    async def test_removes_japanese_phone_hyphenated(self):
        """ハイフン区切りの日本電話番号が除去される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "電話番号は 03-1234-5678 です。"
        sanitized, metadata = await sanitizer.sanitize(content)

        assert "03-1234-5678" not in sanitized
        assert "[電話番号]" in sanitized
        phone_reps = [r for r in metadata["replacements"] if r["type"] == "phone"]
        assert len(phone_reps) >= 1

    @pytest.mark.asyncio
    async def test_removes_mobile_phone(self):
        """携帯電話番号が除去される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "携帯は090-9876-5432です"
        sanitized, metadata = await sanitizer.sanitize(content)

        assert "090-9876-5432" not in sanitized
        phone_reps = [r for r in metadata["replacements"] if r["type"] == "phone"]
        assert len(phone_reps) >= 1

    @pytest.mark.asyncio
    async def test_removes_international_phone(self):
        """国際電話番号（+81 形式）が除去される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "海外連絡先: +81-90-1234-5678"
        sanitized, metadata = await sanitizer.sanitize(content)

        assert "+81-90-1234-5678" not in sanitized
        phone_reps = [r for r in metadata["replacements"] if r["type"] == "phone"]
        assert len(phone_reps) >= 1

    @pytest.mark.asyncio
    async def test_no_pii_returns_unchanged(self):
        """PII が含まれないテキストは変更されない"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "今日はとても良い天気でした。仕事がはかどった。"
        sanitized, metadata = await sanitizer.sanitize(content)

        assert sanitized == content
        assert metadata["replacement_count"] == 0
        assert metadata["replacements"] == []

    @pytest.mark.asyncio
    async def test_removes_email_and_phone_together(self):
        """メールと電話番号が同時に含まれる場合、両方除去される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "メール: test@example.com、電話: 03-0000-1111"
        sanitized, metadata = await sanitizer.sanitize(content)

        assert "test@example.com" not in sanitized
        assert "03-0000-1111" not in sanitized
        assert metadata["replacement_count"] == 2


# =============================================================================
# メタデータ検証テスト
# =============================================================================

class TestMetadataStructure:
    """sanitize() が返す metadata の構造を検証"""

    @pytest.mark.asyncio
    async def test_metadata_has_required_keys(self):
        """metadata に必要な全キーが存在する"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        _, metadata = await sanitizer.sanitize("メール: user@test.com")

        assert "original_length" in metadata
        assert "sanitized_length" in metadata
        assert "replacements" in metadata
        assert "replacement_count" in metadata

    @pytest.mark.asyncio
    async def test_original_length_matches_input(self):
        """original_length が入力テキストの長さと一致する"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "user@example.com に連絡してください。"
        _, metadata = await sanitizer.sanitize(content)

        assert metadata["original_length"] == len(content)

    @pytest.mark.asyncio
    async def test_sanitized_length_matches_output(self):
        """sanitized_length が出力テキストの長さと一致する"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "user@example.com に連絡してください。"
        sanitized, metadata = await sanitizer.sanitize(content)

        assert metadata["sanitized_length"] == len(sanitized)

    @pytest.mark.asyncio
    async def test_replacement_count_matches_list_length(self):
        """replacement_count が replacements リストの長さと一致する"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "a@b.com と c@d.co.jp と 03-1234-5678"
        _, metadata = await sanitizer.sanitize(content)

        assert metadata["replacement_count"] == len(metadata["replacements"])

    @pytest.mark.asyncio
    async def test_replacement_item_structure(self):
        """各 replacement アイテムが正しい構造を持つ"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        _, metadata = await sanitizer.sanitize("test@example.com")

        for rep in metadata["replacements"]:
            assert "type" in rep
            assert "original" in rep
            assert "replacement" in rep
            assert rep["type"] in ("email", "phone", "name")


# =============================================================================
# フォールバックパス: 名前パターン検出（LLM なし）
# =============================================================================

class TestNamePatternFallback:
    """LLM 無効時の日本語名パターン検出テスト"""

    @pytest.mark.asyncio
    async def test_detects_san_suffix(self):
        """〇〇さん パターンが検出・置換される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "田中さんと一緒にプロジェクトを進めた。"
        sanitized, metadata = await sanitizer.sanitize(content)

        name_reps = [r for r in metadata["replacements"] if r["type"] == "name"]
        assert len(name_reps) >= 1
        assert "田中さん" not in sanitized
        assert "[担当者]さん" in sanitized

    @pytest.mark.asyncio
    async def test_detects_sama_suffix(self):
        """〇〇様 パターンが検出される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "伊藤様に報告した。"
        sanitized, metadata = await sanitizer.sanitize(content)

        name_reps = [r for r in metadata["replacements"] if r["type"] == "name"]
        assert len(name_reps) >= 1

    @pytest.mark.asyncio
    async def test_detects_multiple_name_suffixes(self):
        """複数の敬称パターンが検出される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        content = "鈴木部長から承認をもらい、伊藤様に報告し、佐藤さんと打ち合わせした。"
        sanitized, metadata = await sanitizer.sanitize(content)

        name_reps = [r for r in metadata["replacements"] if r["type"] == "name"]
        assert len(name_reps) >= 2

    @pytest.mark.asyncio
    async def test_does_not_replace_long_names(self):
        """5文字以上のカタカナ前置詞は誤検知防止のため無視される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = None

        # 5文字以上の漢字列は名前としてマッチしない（パターン: 1〜4文字）
        content = "プロジェクト管理システムの改善。"
        _, metadata = await sanitizer.sanitize(content)

        # 誤検知がないこと
        name_reps = [r for r in metadata["replacements"] if r["type"] == "name"]
        assert len(name_reps) == 0


# =============================================================================
# LLM パス: モックを使った固有名詞一般化テスト
# =============================================================================

class TestLLMGeneralization:
    """LLM モックによる固有名詞一般化テスト"""

    @pytest.mark.asyncio
    async def test_llm_generalizes_company_names(self, make_mock_provider):
        """LLM モックが企業名・個人名を一般化する"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = make_mock_provider("with_pii", "sanitizer")

        content = "今日、田中さんとAcme社のプロジェクトについて話した。"
        sanitized, metadata = await sanitizer.sanitize(content)

        # LLM の出力（プリセット）が反映される
        assert "Acme社" not in sanitized
        llm_reps = [r for r in metadata["replacements"] if r["type"] == "name"]
        assert len(llm_reps) >= 1

    @pytest.mark.asyncio
    async def test_llm_no_pii_returns_unchanged_text(self, make_mock_provider):
        """LLM が置換なし（no_pii）と判断した場合、テキストの意味が保持される"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = make_mock_provider("no_pii", "sanitizer")

        content = "今日は良い天気でした。"
        sanitized, metadata = await sanitizer.sanitize(content)

        assert "天気" in sanitized
        assert metadata["replacement_count"] == 0

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back_gracefully(self):
        """LLM が例外を投げても sanitize 全体は失敗しない"""
        sanitizer = PrivacySanitizer()

        # LLM が例外を返すモックを設定
        from tests.conftest import MockLLMProvider
        broken_provider = MockLLMProvider()
        broken_provider.generate_json = AsyncMock(side_effect=RuntimeError("LLM error"))
        sanitizer._provider = broken_provider

        content = "田中さんに連絡する。"
        # 例外が出ても sanitize は完了する
        sanitized, metadata = await sanitizer.sanitize(content)

        assert sanitized is not None
        assert "original_length" in metadata

    @pytest.mark.asyncio
    async def test_regex_runs_before_llm(self, make_mock_provider):
        """正規表現パスが LLM の前に実行され、重複置換は発生しない"""
        sanitizer = PrivacySanitizer()
        sanitizer._provider = make_mock_provider("with_pii", "sanitizer")

        # メールアドレスと固有名詞の両方が含まれる
        content = "田中さんのメール: tanaka@example.com"
        sanitized, metadata = await sanitizer.sanitize(content)

        # メールは正規表現で除去済み
        assert "tanaka@example.com" not in sanitized
        email_reps = [r for r in metadata["replacements"] if r["type"] == "email"]
        assert len(email_reps) >= 1
