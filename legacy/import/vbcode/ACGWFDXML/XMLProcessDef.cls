VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "XMLProcessDef"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit
'/ current XML definition version
Private Const mcstrXMLVersion = "2.0"
'/ XML definition version that is being loaded
Private mstrVersion As String
Private moTaskTemplates As TaskTemplates
Private moProcessTemplate As ProcessTemplate

'/ mapping colleciton used to convert GUID to ID
Private mcolIDMAP As Collection

'/ indicates operating in 2.0 compatability mode (no versioning support)
Private mfCompatMode As Boolean

'/ saves the process definition to an XML file
Public Function FileSaveXML(FileName As String, oProcessDef As ProcessDef) As Boolean
    '/ function deprecated - this should never be called any more
    FileSaveXML = False
End Function
'/ sets up the GUID to ID map
Private Sub CreateGUID2ID(oProcessDef As ProcessDef)
    Set mcolIDMAP = New Collection
    Dim oTaskDef As TaskDef
    Dim oRoutingDef As RoutingDef
    Dim lngNewID As Long
    For Each oTaskDef In oProcessDef.Tasks
        lngNewID = lngNewID + 1
        mcolIDMAP.Add lngNewID, oTaskDef.GUID
    Next
    For Each oRoutingDef In oProcessDef.Routings
        lngNewID = lngNewID + 1
        mcolIDMAP.Add lngNewID, oRoutingDef.GUID
    Next
End Sub

'/ returns the Long ID version of the GUID
Private Function GUID2ID(GUID As String) As Long
    GUID2ID = mcolIDMAP(GUID)
End Function

'/ returns the GUID version of an ID
Private Function ID2GUID(ID As Long) As String
    On Error Resume Next
    ID2GUID = mcolIDMAP("@" & ID)
    If Err.Number <> 0 Then
        Err.Clear
        Dim strGUID As String
        strGUID = CreateGUID
        mcolIDMAP.Add strGUID, "@" & ID
        ID2GUID = strGUID
    End If
End Function

'/ fills the node with the XML of the processdef
Public Function ProcessXML(oProcessDef As ProcessDef, oRoot As MSXML2.IXMLDOMNode) As Boolean
    Dim oNode As MSXML2.IXMLDOMNode
    Dim oProp As Property
    Dim fOk As Boolean
    
    '/ setup the id mapper
    CreateGUID2ID oProcessDef
        
    Set oNode = XMLNode(oRoot, "ProcessDef")
    'oRoot.appendChild oNode
    
    '/ XMLAttr oNode, "GUID", GUID2ID(oProcessDef.GUID)
    
    '# this can be empty
    If Not (oProcessDef.FirstTask Is Nothing) Then
    
        XMLAttr oNode, "FirstTask", GUID2ID(oProcessDef.FirstTask.GUID)
    End If
    
    XMLAttr oNode, "ProcessTemplate", oProcessDef.ProcessTemplate
    
    PropertiesXML oProcessDef.PropertyGroup, oNode
    
    If Not TasksXML(oProcessDef.Tasks, oNode) Then
        Exit Function
    ElseIf Not RoutingsXML(oProcessDef.Routings, oNode) Then
        Exit Function
    End If
    ProcessXML = True
    
End Function
Private Function PropertiesXML(oPG As PropertyGroup, oRoot As IXMLDOMNode) As Boolean
    Dim oPropPersist As XMLPropPersist
    Set oPropPersist = New XMLPropPersist
    PropertiesXML = oPropPersist.PropertiesXML(oPG, oRoot)
End Function
Private Function TasksXML(oTasks As Tasks, oRoot As MSXML2.IXMLDOMNode) As Boolean
    Dim oTaskDef As TaskDef
    Dim oNode As MSXML2.IXMLDOMNode
    
    Set oNode = XMLNode(oRoot, "TaskDefs")
    'oRoot.appendChild oNode
    
    For Each oTaskDef In oTasks
        TaskXML oTaskDef, oNode
    Next
    
    TasksXML = True
End Function

Private Function TaskXML(oTaskDef As TaskDef, oRoot As MSXML2.IXMLDOMNode) As Boolean
    Dim oNode As MSXML2.IXMLDOMNode
    
    Set oNode = XMLNode(oRoot, "TaskDef")
    'oRoot.appendChild oNode
    
    With oTaskDef
        XMLAttr oNode, "GUID", GUID2ID(.GUID)
        XMLAttr oNode, "Height", .Height
        XMLAttr oNode, "Left", .Left
        XMLAttr oNode, "Top", .Top
        XMLAttr oNode, "Width", .Width
        XMLAttr oNode, "TaskTemplate", .TaskTemplate
    End With
    
    
    TaskXML = PropertiesXML(oTaskDef.PropertyGroup, oNode)
End Function

Private Function RoutingsXML(oRoutings As Routings, oRoot As MSXML2.IXMLDOMNode) As Boolean
    Dim oRoutingDef As RoutingDef
    Dim oNode As MSXML2.IXMLDOMNode
    
    Set oNode = XMLNode(oRoot, "RoutingDefs")
    'oRoot.appendChild oNode
    
    For Each oRoutingDef In oRoutings
        RoutingXML oRoutingDef, oNode
    Next
    
    RoutingsXML = True
End Function

Private Function RoutingXML(oRoutingDef As RoutingDef, oRoot As MSXML2.IXMLDOMNode) As Boolean
    Dim oNode As MSXML2.IXMLDOMNode

    Set oNode = XMLNode(oRoot, "RoutingDef")
    'oRoot.appendChild oNode
    
    With oRoutingDef
        XMLAttr oNode, "GUID", GUID2ID(.GUID)
        XMLAttr oNode, "TaskDestGUID", GUID2ID(.TaskDest.GUID)
        XMLAttr oNode, "TaskOrgGUID", GUID2ID(.TaskOrg.GUID)
    End With
    
    If Not PointsXML(oRoutingDef, oNode) Then
        Exit Function
    End If
    RoutingXML = PropertiesXML(oRoutingDef.PropertyGroup, oNode)
End Function

Private Function PointsXML(oRoutingDef As RoutingDef, oRoot As MSXML2.IXMLDOMNode) As Boolean
    Dim oNode As IXMLDOMNode
    Dim lngCount As Long
    Dim sglX As Single
    Dim sglY As Single
    
    Set oNode = XMLNode(oRoot, "Points")
    'oRoot.appendChild oNode
    
    For lngCount = 1 To oRoutingDef.PointCount
        oRoutingDef.Point sglX, sglY, lngCount
        PointXML sglX, sglY, oNode
    Next
    PointsXML = True
End Function

Private Function PointXML(X As Single, Y As Single, oRoot As MSXML2.IXMLDOMNode) As Boolean
    Dim oNode As IXMLDOMNode
    
    Set oNode = XMLNode(oRoot, "Point")
    'oRoot.appendChild oNode
    
    XMLAttr oNode, "X", X
    XMLAttr oNode, "Y", Y
    PointXML = True
End Function

Public Function FileLoadXML(FileName As String, oProcessDef As ProcessDef, oTaskTemplates As TaskTemplates, oProcessTemplates As ProcessTemplates) As Boolean
    On Error GoTo Err_Handler
    mfCompatMode = True
    Dim oDoc As MSXML2.DOMDocument
    Dim oRoot As MSXML2.IXMLDOMNode
    Set oDoc = New MSXML2.DOMDocument
    Set moTaskTemplates = oTaskTemplates
    Set mcolIDMAP = New Collection
    oDoc.Load FileName
    
    Set oRoot = oDoc.firstChild
    
    If oRoot.nodeName <> "ACGWFDNative" Then
        FileLoadXML = False
        Exit Function
    End If
    
    mstrVersion = oRoot.Attributes.getNamedItem("Version").nodeValue
    
    Dim oNode As IXMLDOMNode
    
    If mstrVersion = mcstrXMLVersion Then
        FileLoadXML = XMLProcess(oProcessDef, oRoot.firstChild, oProcessTemplates, oTaskTemplates)
    Else
        '/ bad version number
        FileLoadXML = False
    End If
    Set moTaskTemplates = Nothing
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function

Public Function XMLProcess(oProcessDef As ProcessDef, oRoot As IXMLDOMNode, oProcessTemplates As ProcessTemplates, oTaskTemplates As TaskTemplates) As Boolean
    On Error GoTo Err_Handler
    Set mcolIDMAP = New Collection
    Dim oNode As IXMLDOMNode
    
    If StrComp(oRoot.nodeName, "ProcessDef", vbTextCompare) <> 0 Then
        Exit Function
    End If
    
    oProcessDef.ProcessTemplate = GetNodeAttr(oRoot, "ProcessTemplate")
    
    On Error Resume Next
    Set moProcessTemplate = oProcessTemplates(oProcessDef.ProcessTemplate)
    Set moTaskTemplates = oTaskTemplates
    On Error GoTo 0
    If Not (moProcessTemplate Is Nothing) Then
        '# copy default props
        CopyProps moProcessTemplate.ProcessProperties, oProcessDef.PropertyGroup
    End If
    '# get each subcategory first
    For Each oNode In oRoot.childNodes
        Select Case LCase$(oNode.nodeName)
            Case "properties"
                If Not XMLProperties(oProcessDef.PropertyGroup, oNode) Then
                    Exit Function
                End If
            Case "taskdefs"
                If Not XMLTasks(oProcessDef.Tasks, oNode) Then
                    Exit Function
                End If
            Case "routingdefs"
                If Not XMLRoutings(oProcessDef.Routings, oNode) Then
                    Exit Function
                End If
            Case Else
                '# bad XML
                Exit Function
        End Select
    Next
    
    '# this can be empty / not set
    On Error Resume Next
    Set oProcessDef.FirstTask = oProcessDef.Tasks(GetNodeAttr(oRoot, "FirstTask"))
    On Error GoTo 0
    Set moProcessTemplate = Nothing
    Set moTaskTemplates = Nothing
    XMLProcess = True
    Exit Function
Err_Handler:
    Stop
    Resume 0

End Function

Private Function XMLProperties(oPG As PropertyGroup, oRoot As MSXML2.IXMLDOMNode) As Boolean
    Dim oXMLPropPersist As XMLPropPersist
    Set oXMLPropPersist = New XMLPropPersist
    XMLProperties = oXMLPropPersist.XMLProperties(oPG, oRoot)
    Exit Function
Err_Handler:
    Stop
    Resume 0

End Function
Private Function XMLTasks(oTasks As Tasks, oRoot As IXMLDOMNode) As Boolean
    On Error GoTo Err_Handler
    If StrComp(oRoot.nodeName, "taskdefs", vbTextCompare) <> 0 Then
        Exit Function
    End If
    Dim oNode As IXMLDOMNode
    For Each oNode In oRoot.childNodes
        If Not XMLTask(oTasks, oNode) Then
            Exit Function
        End If
    Next
    XMLTasks = True
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function

Private Function XMLTask(oTasks As Tasks, oRoot As IXMLDOMNode) As Boolean
    On Error GoTo Err_Handler
    Dim oNode As IXMLDOMNode
    Dim fOk As Boolean
    If StrComp(oRoot.nodeName, "taskdef", vbTextCompare) <> 0 Then
        Exit Function
    End If
    
    Dim oTaskDef As TaskDef
    If mfCompatMode Then
        Set oTaskDef = oTasks.Add(GetNodeAttr(oRoot, "GUID"))
    Else
        Set oTaskDef = oTasks.Add(ID2GUID(GetNodeAttr(oRoot, "GUID")))
    End If
    With oTaskDef
        .Height = GetNodeAttr(oRoot, "Height")
        .Left = GetNodeAttr(oRoot, "Left")
        .TaskTemplate = GetNodeAttr(oRoot, "TaskTemplate")
        .Top = GetNodeAttr(oRoot, "Top")
        .Width = GetNodeAttr(oRoot, "Width")
        .TaskTemplate = GetNodeAttr(oRoot, "TaskTemplate")
    End With
    If Not (moProcessTemplate Is Nothing) Then
        Debug.Print "Copying process template values"
        CopyProps moProcessTemplate.CommonTaskProperties, oTaskDef.PropertyGroup
    End If
    On Error Resume Next
    Dim oTaskTemplate As TaskTemplate
    
    Set oTaskTemplate = moTaskTemplates(oTaskDef.TaskTemplate)
    On Error GoTo Err_Handler
    
    If Not (oTaskTemplate Is Nothing) Then
        Debug.Print "Copying task template values"
        CopyProps oTaskTemplate.PropertyGroup, oTaskDef.PropertyGroup
    End If
    For Each oNode In oRoot.childNodes
        fOk = XMLProperties(oTaskDef.PropertyGroup, oNode)
        If Not fOk Then Exit For
    Next
    If fOk Then
        '// update props
        If Not (moProcessTemplate Is Nothing) Then
            updateLockedProps oTaskDef.PropertyGroup, moProcessTemplate.CommonTaskProperties
        End If
        If Not (oTaskTemplate Is Nothing) Then
            updateLockedProps oTaskDef.PropertyGroup, oTaskTemplate.PropertyGroup
        End If
        
    End If
    XMLTask = fOk
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function

Private Sub updateLockedProps(propsToUpdate As PropertyGroup, propsTemplate As PropertyGroup)
    Dim ps As Properties
    Dim p As Property
    For Each ps In propsTemplate
        For Each p In ps
            If p.Locked Then
                propsToUpdate.Item(ps.Name).Item(p.Name).Value = p.Value
                propsToUpdate.Item(ps.Name).Item(p.Name).Locked = p.Locked
            End If
        Next
    Next
End Sub

Private Function XMLRoutings(oRoutings As Routings, oRoot As IXMLDOMNode) As Boolean
    On Error GoTo Err_Handler
    If StrComp(oRoot.nodeName, "routingdefs", vbTextCompare) <> 0 Then
        Exit Function
    End If
    Dim oNode As IXMLDOMNode
    For Each oNode In oRoot.childNodes
        Select Case LCase$(oNode.nodeName)
            Case "routingdef"
                If Not XMLRouting(oRoutings, oNode) Then
                    Exit Function
                End If
            Case Else
                '# bad xml
                Exit Function
        End Select
    Next
    
    XMLRoutings = True
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function
Private Function XMLRouting(oRoutings As Routings, oRoot As IXMLDOMNode) As Boolean
    On Error GoTo Err_Handler
    If StrComp(oRoot.nodeName, "routingdef", vbTextCompare) <> 0 Then
        Exit Function
    End If
    
    Dim oRouting As RoutingDef
    Dim oNode As IXMLDOMNode
    If mfCompatMode Then
    
        Set oRouting = oRoutings.Add(oRoutings.ProcessDef.Tasks(GetNodeAttr(oRoot, "TaskOrgGUID")), oRoutings.ProcessDef.Tasks(GetNodeAttr(oRoot, "TaskDestGUID")), GetNodeAttr(oRoot, "GUID"))
    Else
        Set oRouting = oRoutings.Add(oRoutings.ProcessDef.Tasks(ID2GUID(GetNodeAttr(oRoot, "TaskOrgGUID"))), oRoutings.ProcessDef.Tasks(ID2GUID(GetNodeAttr(oRoot, "TaskDestGUID"))), ID2GUID(GetNodeAttr(oRoot, "GUID")))
    End If
    If Not (moProcessTemplate Is Nothing) Then
        CopyProps moProcessTemplate.CommonRoutingProperties, oRouting.PropertyGroup
    End If
    
    
    For Each oNode In oRoot.childNodes
        Select Case LCase$(oNode.nodeName)
            Case "properties"
                If Not XMLProperties(oRouting.PropertyGroup, oNode) Then
                    Exit Function
                End If
            Case "points"
                If Not XMLPoints(oRouting, oNode) Then
                    Exit Function
                End If
            Case Else
                '# bad xml
                Exit Function
        End Select
    Next
    XMLRouting = True
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function

Private Function XMLPoints(oRouting As RoutingDef, oRoot As IXMLDOMNode) As Boolean
    On Error GoTo Err_Handler
    If StrComp(oRoot.nodeName, "points", vbTextCompare) <> 0 Then
        Exit Function
    End If
    Dim oNode As IXMLDOMNode
    For Each oNode In oRoot.childNodes
        Select Case LCase$(oNode.nodeName)
            Case "point"
                If Not XMLPoint(oRouting, oNode) Then
                    Exit Function
                End If
            Case Else
                '# bad xml
                Exit Function
        End Select
    Next
    XMLPoints = True
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function

Private Function XMLPoint(oRouting As RoutingDef, oRoot As IXMLDOMNode) As Boolean
    On Error GoTo Err_Handler
    If StrComp(oRoot.nodeName, "point", vbTextCompare) <> 0 Then
        Exit Function
    End If
    oRouting.AddPoint GetNodeAttr(oRoot, "X"), GetNodeAttr(oRoot, "Y")
    XMLPoint = True
    Exit Function
Err_Handler:
    Stop
    Resume 0
End Function

