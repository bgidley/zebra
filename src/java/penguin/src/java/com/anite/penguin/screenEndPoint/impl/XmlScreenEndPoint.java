package com.anite.penguin.screenEndPoint.impl;

import java.io.File;
import java.io.IOException;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import org.apache.avalon.framework.activity.Initializable;
import org.apache.avalon.framework.context.Context;
import org.apache.avalon.framework.context.ContextException;
import org.apache.avalon.framework.context.Contextualizable;
import org.apache.avalon.framework.logger.AbstractLogEnabled;
import org.apache.turbine.services.avaloncomponent.AvalonComponentService;
import org.jdom.Document;
import org.jdom.Element;
import org.jdom.JDOMException;
import org.jdom.input.SAXBuilder;
import com.anite.penguin.exceptions.BadEndpointConfigurationException;
import com.anite.penguin.screenEndPoint.api.ScreenEndPoint;

/**
 * Load the endpoint from endpoints.xml in WEB-INF/conf Created May 12, 2004
 */
public class XmlScreenEndPoint extends AbstractLogEnabled implements
        ScreenEndPoint, Initializable, Contextualizable {

    /**
     * The XML file name to read
     */
    private static final String XML_FILE_NAME = "endpoints.xml";

    private String applicationRoot;

    private Map endPoints = new HashMap();

    /**
     * Gets endpoint for passed screen from the endpoints.xml file in
     * WEB-INF/conf
     * 
     * @see com.anite.penguin.screenEndPoint.api.ScreenEndPoint#getEndPoint(java.lang.String)
     */
    public String getEndPoint(String screen) {
        return (String) endPoints.get(screen);
    }

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.avalon.framework.activity.Initializable#initialize()
     */
    public void initialize() throws Exception {
        //Load the XML File and initialise the in memory object structure
        File file = new File(applicationRoot + "/WEB-INF/conf/"
                + XML_FILE_NAME);
        if (file.exists()) {
            Document document = getDocument(file);
            Element rootElement = document.getRootElement();
            
            Iterator i = rootElement.getChildren().iterator();
            while (i.hasNext()){
                Element screen = (Element) i.next();                
                endPoints.put(screen.getAttribute("name").getValue(), screen.getAttribute("endpoint").getValue());
            }
            
        } else {
            this.getLogger().error("endpoint file does not exist");
            throw new BadEndpointConfigurationException(
                    "endpoint file does not exist");
        }
    }

    /**
     * Construct JDom document for passed file 
     * @param file
     * @return
     */
    private Document getDocument(File file) throws JDOMException, IOException {
        this.getLogger().debug("Called getDocument");
        SAXBuilder builder = new SAXBuilder();
        // TODO write schema so we can set this to true
        builder.setValidation(true);
        try {
            Document document = builder.build(file);
            return document;
        } catch (JDOMException e) {
            this.getLogger().error(
                    file.getAbsolutePath() + " is not well-formed. "
                            + e.getMessage());
            throw e;
        } catch (IOException e) {
            this.getLogger().error(
                    "Could not check " + file.getAbsolutePath() + " because "
                            + e.getMessage());
            throw e;
        }
    }

    /*
     * (non-Javadoc)
     * 
     * @see org.apache.avalon.framework.context.Contextualizable#contextualize(org.apache.avalon.framework.context.Context)
     */
    public void contextualize(Context context) throws ContextException {
        this.getLogger().debug("contextualize");
        applicationRoot = (String) context
                .get(AvalonComponentService.COMPONENT_APP_ROOT);
    }
}