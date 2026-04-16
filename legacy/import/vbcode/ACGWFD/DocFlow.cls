VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "DocFlow"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

'// documents a workflow as an html page

Public Sub DocProcess(oProcessDef As ProcessDef, fileName As String, showLocked As Boolean)
    Dim html As MSXML2.IXMLDOMNode
    Set html = XMLDoc("html")
    
    docProcessDef createBody(html, oProcessDef), oProcessDef, showLocked
    saveDoc html.ownerDocument, fileName
End Sub
Private Function createBody(html As IXMLDOMNode, oProcessDef As ProcessDef) As IXMLDOMNode
    Dim nHead As IXMLDOMNode
    Set nHead = XMLNode(html, "head")
    Dim nStyle As IXMLDOMNode
    Set nStyle = XMLNode(nHead, "style")
    XMLAttr nStyle, "type", "text/css"
    nStyle.Text = "* {font-family:verdana;} td,table {border-style:solid;border-width:1px;margin:0px;padding:2px;border-spacing:0px;border-collapse:collapse;}"
    XMLNode nHead, "title", "Documentation for Process """ & speech(oProcessDef.Name) & """"
    Set createBody = XMLNode(html, "body")
End Function
Private Function docProcessDef(doc As IXMLDOMNode, oProcessDef As ProcessDef, showLocked As Boolean)
    Dim nTable As IXMLDOMNode
    Set nTable = XMLNode(doc, "table")
    Dim nRow As IXMLDOMNode
    Set nRow = XMLNode(nTable, "tr")
    Dim nCell As IXMLDOMNode
    Set nCell = XMLNode(nRow, "td", "Process")
    XMLAttr nCell, "colspan", 3
    docPropGroups nTable, oProcessDef.PropertyGroup, showLocked
    docTasks doc, oProcessDef.Tasks, showLocked
End Function
Private Sub saveDoc(doc As MSXML2.DOMDocument, fileName As String)
    If Dir$(fileName) > "" Then
        Kill fileName
    End If
    doc.save fileName
End Sub
Private Sub docTasks(doc As MSXML2.IXMLDOMNode, oTasks As Tasks, showLocked As Boolean)
    Dim oTaskDef As TaskDef
    Dim nTable As IXMLDOMNode
    Set nTable = XMLNode(doc, "table")
    Dim nRow As IXMLDOMNode
    Dim nCell As IXMLDOMNode
    For Each oTaskDef In oTasks
        Set nRow = XMLNode(nTable, "tr")
        Set nCell = XMLNode(nRow, "td")
        docTask nCell, oTaskDef, showLocked
    Next
End Sub
Private Sub docTask(doc As MSXML2.IXMLDOMNode, oTaskDef As TaskDef, showLocked As Boolean)
    Dim nTable As IXMLDOMNode
    Dim nRow As IXMLDOMNode
    Dim nCell As IXMLDOMNode
    Set nTable = XMLNode(doc, "table")
    Set nRow = XMLNode(nTable, "tr")
    Set nCell = XMLNode(nRow, "td", "Task")
    XMLAttr nCell, "colspan", 3
    docPropGroups nTable, oTaskDef.PropertyGroup, showLocked
    
    docTaskRoutings nTable, oTaskDef, showLocked
End Sub
Private Sub docTaskRoutings(doc As MSXML2.IXMLDOMNode, oTaskDef As TaskDef, showLocked As Boolean)
    Dim nRow As IXMLDOMNode
    Dim nCell As IXMLDOMNode
    Dim oRouting As RoutingDef
    If oTaskDef.RoutingOut.Count > 0 Then
        Set nRow = XMLNode(doc, "tr")
        Set nCell = XMLNode(nRow, "td", "Routing Out")
        XMLAttr nCell, "colspan", 3
        For Each oRouting In oTaskDef.RoutingOut
            docRouting doc, oRouting, oRouting.TaskDest, showLocked
        Next
    End If
    If oTaskDef.RoutingIn.Count > 0 Then
        Set nRow = XMLNode(doc, "tr")
        Set nCell = XMLNode(nRow, "td", "Routing In")
        XMLAttr nCell, "colspan", 3
        For Each oRouting In oTaskDef.RoutingIn
            docRouting doc, oRouting, oRouting.TaskOrg, showLocked
        Next
    End If
End Sub
Private Sub docRouting(doc As MSXML2.IXMLDOMNode, oRouting As RoutingDef, oTaskDef As TaskDef, showLocked As Boolean)
    Dim nRow As IXMLDOMNode
    Set nRow = XMLNode(doc, "tr")
    XMLAttr XMLNode(nRow, "td", oTaskDef.Name), "colspan", 3
    docPropGroups doc, oRouting.PropertyGroup, showLocked
End Sub
Private Sub docPropGroups(doc As MSXML2.IXMLDOMNode, oPropGroup As PropertyGroup, showLocked As Boolean)
    Dim oProperties As Properties
    
    For Each oProperties In oPropGroup
        docProps doc, oProperties, showLocked
    Next
End Sub

Private Sub docProps(doc As MSXML2.IXMLDOMNode, oProps As Properties, showLocked As Boolean)
    If oProps.Count = 0 Then Exit Sub
    Dim oProp As Property
    Dim fDoProps As Boolean
    For Each oProp In oProps
        If Len(oProp.Value) > 0 Then
            If Not (showLocked = False And oProp.Locked = True) Then
                fDoProps = True
                Exit For
            End If
        End If
    Next
    If Not fDoProps Then Exit Sub
    Dim nRow As IXMLDOMNode
    Dim nCell As IXMLDOMNode
    Set nRow = XMLNode(doc, "tr")
    Set nCell = XMLNode(nRow, "td", oProps.Name)
    Dim iPropCount As Integer
    Dim nCurrent As IXMLDOMNode
    Set nCurrent = nRow
    For Each oProp In oProps
        If docProp(nCurrent, oProp, showLocked) Then
            iPropCount = iPropCount + 1
            Set nCurrent = XMLNode(doc, "tr")
        End If
        
    Next
    If iPropCount > 1 Then
        XMLAttr nCell, "rowspan", iPropCount
    End If
End Sub

Private Function docProp(doc As MSXML2.IXMLDOMNode, oProp As Property, showLocked As Boolean) As Boolean
    docProp = False
    If Len(oProp.Value) = 0 Or (showLocked = False And oProp.Locked) Then Exit Function
    XMLNode doc, "td", oProp.Name
    XMLNode doc, "td", oProp.Value
    docProp = True
End Function

