package com.anite.antelope.modules.screens.formSample;

import org.apache.turbine.modules.screens.VelocityScreen;
import org.apache.turbine.util.RunData;
import org.apache.velocity.context.Context;

import com.anite.penguin.form.Field;
import com.anite.penguin.modules.tools.FormTool;

/**
 * Created 14-May-2004
 */
public class SimpleForm extends VelocityScreen {

    private static final String TEXTFIELD = "textfield";

    /**
     * Set up the defaults for this form
     */
    protected void doBuildTemplate(RunData data, Context context)
            throws Exception {

        FormTool form = (FormTool) context.get(FormTool.DEFAULT_TOOL_NAME);

        Field field = (Field) form.getFields().get(TEXTFIELD);
        field.setDefaultValue("Default Text Value");

    }
}