"""Tests for human interaction task actions."""


from zebra_tasks.human import DataDisplayAction, DataEntryAction


class TestDataEntryAction:
    """Tests for DataEntryAction."""

    async def test_data_entry_basic(self, mock_context, mock_task):
        """Test basic data entry action."""
        action = DataEntryAction()
        mock_task.properties = {
            "title": "User Registration",
            "fields": [
                {"name": "username", "label": "Username", "type": "text", "required": True},
                {"name": "email", "label": "Email", "type": "text"},
            ],
            "output_key": "user_data",
        }

        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["status"] == "waiting_for_input"
        assert result.output["title"] == "User Registration"
        assert len(result.output["fields"]) == 2

        # Check that metadata was stored
        entry_key = f"__data_entry_{mock_task.id}__"
        assert entry_key in mock_context.process.properties
        assert mock_context.process.properties[entry_key]["status"] == "waiting"

    async def test_data_entry_no_fields(self, mock_context, mock_task):
        """Test data entry with no fields fails."""
        action = DataEntryAction()
        mock_task.properties = {"title": "Empty Form"}

        result = await action.run(mock_task, mock_context)

        assert not result.success
        assert "No fields defined" in result.error

    async def test_data_entry_invalid_field_no_name(self, mock_context, mock_task):
        """Test data entry with invalid field (missing name) fails."""
        action = DataEntryAction()
        mock_task.properties = {
            "title": "Bad Form",
            "fields": [{"label": "Field 1"}],
        }

        result = await action.run(mock_task, mock_context)

        assert not result.success
        assert "missing required 'name'" in result.error

    async def test_data_entry_invalid_field_no_label(self, mock_context, mock_task):
        """Test data entry with invalid field (missing label) fails."""
        action = DataEntryAction()
        mock_task.properties = {
            "title": "Bad Form",
            "fields": [{"name": "field1"}],
        }

        result = await action.run(mock_task, mock_context)

        assert not result.success
        assert "missing required 'label'" in result.error

    async def test_data_entry_invalid_type(self, mock_context, mock_task):
        """Test data entry with invalid field type fails."""
        action = DataEntryAction()
        mock_task.properties = {
            "title": "Bad Form",
            "fields": [
                {"name": "field1", "label": "Field 1", "type": "invalid_type"},
            ],
        }

        result = await action.run(mock_task, mock_context)

        assert not result.success
        assert "invalid type" in result.error

    async def test_data_entry_select_without_options(self, mock_context, mock_task):
        """Test data entry with select field but no options fails."""
        action = DataEntryAction()
        mock_task.properties = {
            "title": "Bad Form",
            "fields": [
                {"name": "choice", "label": "Choose", "type": "select"},
            ],
        }

        result = await action.run(mock_task, mock_context)

        assert not result.success
        assert "must have 'options'" in result.error

    async def test_data_entry_all_field_types(self, mock_context, mock_task):
        """Test data entry with all field types."""
        action = DataEntryAction()
        mock_task.properties = {
            "title": "Complete Form",
            "fields": [
                {"name": "text_field", "label": "Text", "type": "text"},
                {"name": "num_field", "label": "Number", "type": "number"},
                {"name": "bool_field", "label": "Boolean", "type": "boolean", "default": True},
                {"name": "date_field", "label": "Date", "type": "date"},
                {
                    "name": "select_field",
                    "label": "Select",
                    "type": "select",
                    "options": ["A", "B"],
                },
            ],
        }

        result = await action.run(mock_task, mock_context)

        assert result.success
        assert len(result.output["fields"]) == 5

    async def test_data_entry_on_construct(self, mock_context, mock_task):
        """Test on_construct lifecycle hook."""
        action = DataEntryAction()
        mock_task.properties = {
            "title": "Test",
            "fields": [{"name": "test", "label": "Test"}],
        }

        await action.on_construct(mock_task, mock_context)

        waiting_key = f"__waiting_for_human_{mock_task.id}__"
        assert mock_context.process.properties[waiting_key] is True

    async def test_data_entry_on_destruct(self, mock_context, mock_task):
        """Test on_destruct lifecycle hook."""
        action = DataEntryAction()
        mock_task.properties = {
            "title": "Test",
            "fields": [{"name": "test", "label": "Test"}],
            "output_key": "collected_data",
        }

        # Setup data like it would be after external completion
        mock_task.result = {"test": "value"}
        mock_context.process.properties[f"__waiting_for_human_{mock_task.id}__"] = True
        mock_context.process.properties[f"__data_entry_{mock_task.id}__"] = {"status": "waiting"}

        await action.on_destruct(mock_task, mock_context)

        # Check cleanup
        waiting_key = f"__waiting_for_human_{mock_task.id}__"
        entry_key = f"__data_entry_{mock_task.id}__"
        assert waiting_key not in mock_context.process.properties
        assert entry_key not in mock_context.process.properties

        # Check data was stored
        assert mock_context.process.properties["collected_data"] == {"test": "value"}


class TestDataDisplayAction:
    """Tests for DataDisplayAction."""

    async def test_data_display_basic(self, mock_context, mock_task):
        """Test basic data display action."""
        action = DataDisplayAction()
        mock_task.properties = {
            "title": "Results",
            "message": "Analysis complete",
            "fields": [
                {"label": "Status", "value": "Success"},
                {"label": "Score", "value": "95", "format": "number"},
            ],
            "output_key": "user_ack",
        }

        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["status"] == "waiting_acknowledgment"
        assert result.output["title"] == "Results"
        assert result.output["message"] == "Analysis complete"
        assert len(result.output["fields"]) == 2

        # Check metadata was stored
        display_key = f"__data_display_{mock_task.id}__"
        assert display_key in mock_context.process.properties

    async def test_data_display_no_title(self, mock_context, mock_task):
        """Test data display without title fails."""
        action = DataDisplayAction()
        mock_task.properties = {
            "fields": [{"label": "Test", "value": "value"}],
        }

        result = await action.run(mock_task, mock_context)

        assert not result.success
        assert "No title provided" in result.error

    async def test_data_display_no_fields_or_data(self, mock_context, mock_task):
        """Test data display without fields or data fails."""
        action = DataDisplayAction()
        mock_task.properties = {"title": "Empty Display"}

        result = await action.run(mock_task, mock_context)

        assert not result.success
        assert "No fields or data provided" in result.error

    async def test_data_display_invalid_field(self, mock_context, mock_task):
        """Test data display with invalid field fails."""
        action = DataDisplayAction()
        mock_task.properties = {
            "title": "Bad Display",
            "fields": [{"label": "Missing value"}],
        }

        result = await action.run(mock_task, mock_context)

        assert not result.success
        assert "missing required" in result.error

    async def test_data_display_with_data_dict(self, mock_context, mock_task):
        """Test data display with raw data dict."""
        action = DataDisplayAction()
        mock_task.properties = {
            "title": "Data",
            "data": {"key1": "value1", "key2": 42},
        }

        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["data"] == {"key1": "value1", "key2": 42}

    async def test_data_display_template_resolution(self, mock_context, mock_task):
        """Test template resolution in display fields."""
        action = DataDisplayAction()
        mock_context.process.properties["analysis_score"] = "95"
        mock_context.process.properties["status"] = "complete"

        mock_task.properties = {
            "title": "Results",
            "message": "Analysis is {{status}}",
            "fields": [
                {"label": "Score", "value": "{{analysis_score}}"},
            ],
        }

        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["message"] == "Analysis is complete"
        assert result.output["fields"][0]["value"] == "95"

    async def test_data_display_template_in_data(self, mock_context, mock_task):
        """Test template resolution in data dict."""
        action = DataDisplayAction()
        mock_context.process.properties["name"] = "John"
        mock_context.process.properties["score"] = "100"

        mock_task.properties = {
            "title": "User Info",
            "data": {
                "user_name": "{{name}}",
                "user_score": "{{score}}",
                "nested": {
                    "inner": "{{name}}'s score is {{score}}",
                },
            },
        }

        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["data"]["user_name"] == "John"
        assert result.output["data"]["user_score"] == "100"
        assert result.output["data"]["nested"]["inner"] == "John's score is 100"

    async def test_data_display_with_confirmation(self, mock_context, mock_task):
        """Test data display with confirmation required."""
        action = DataDisplayAction()
        mock_task.properties = {
            "title": "Confirm",
            "fields": [{"label": "Action", "value": "Delete"}],
            "require_confirmation": True,
        }

        result = await action.run(mock_task, mock_context)

        assert result.success
        assert result.output["require_confirmation"] is True

    async def test_data_display_on_construct(self, mock_context, mock_task):
        """Test on_construct lifecycle hook."""
        action = DataDisplayAction()
        mock_task.properties = {
            "title": "Test",
            "fields": [{"label": "Test", "value": "value"}],
        }

        await action.on_construct(mock_task, mock_context)

        waiting_key = f"__waiting_for_human_{mock_task.id}__"
        assert mock_context.process.properties[waiting_key] is True

    async def test_data_display_on_destruct(self, mock_context, mock_task):
        """Test on_destruct lifecycle hook."""
        action = DataDisplayAction()
        mock_task.properties = {
            "title": "Test",
            "fields": [{"label": "Test", "value": "value"}],
            "output_key": "ack_result",
        }

        # Setup data like it would be after external acknowledgment
        mock_task.result = {"acknowledged": True, "feedback": "Looks good"}
        mock_context.process.properties[f"__waiting_for_human_{mock_task.id}__"] = True
        mock_context.process.properties[f"__data_display_{mock_task.id}__"] = {"status": "waiting"}

        await action.on_destruct(mock_task, mock_context)

        # Check cleanup
        waiting_key = f"__waiting_for_human_{mock_task.id}__"
        display_key = f"__data_display_{mock_task.id}__"
        assert waiting_key not in mock_context.process.properties
        assert display_key not in mock_context.process.properties

        # Check acknowledgment was stored
        assert mock_context.process.properties["ack_result"] == {
            "acknowledged": True,
            "feedback": "Looks good",
        }

    async def test_data_display_on_destruct_non_dict_result(self, mock_context, mock_task):
        """Test on_destruct with non-dict result."""
        action = DataDisplayAction()
        mock_task.properties = {
            "title": "Test",
            "fields": [{"label": "Test", "value": "value"}],
            "output_key": "ack_result",
        }

        # Setup with simple result
        mock_task.result = "acknowledged"

        await action.on_destruct(mock_task, mock_context)

        # Check acknowledgment was wrapped
        assert mock_context.process.properties["ack_result"] == {
            "acknowledged": True,
            "result": "acknowledged",
        }
