VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "XMLPropPersist"
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

Public Function PropertiesXML(oPropertyGroup As PropertyGroup, oRoot As MSXML2.IXMLDOMNode) As Boolean
    Dim oProps As Properties
    Dim oProp As Property
    Dim oNode As MSXML2.IXMLDOMNode
    
    
    For Each oProps In oPropertyGroup
        Set oNode = XMLNode(oRoot, "properties")
        oRoot.appendChild oNode
        XMLAttr oNode, "name", oProps.Name
        For Each oProp In oProps
            PropertyXML oProp, oNode
        Next
    Next
    PropertiesXML = True
End Function

Private Function PropertyXML(oProperty As Property, oRoot As MSXML2.IXMLDOMNode) As Boolean
    Dim oNode As MSXML2.IXMLDOMNode
    Set oNode = XMLNode(oRoot, "property")
    oRoot.appendChild oNode
    With oProperty
        XMLAttr oNode, "locked", .Locked
        XMLAttr oNode, "name", .Name
        XMLAttr oNode, "value", FriendlyValue(oProperty)
        XMLAttr oNode, "type", PropTypeToString(.PropertyType)
    End With
End Function
Private Function FriendlyValue(oProperty As Property) As String
    Select Case oProperty.PropertyType
        Case ptBoolean
            FriendlyValue = Format$(oProperty.Value, "Yes/No")
        Case Else
            FriendlyValue = oProperty.Value
    End Select
End Function
Public Function XMLProperties(oPropertyGroup As PropertyGroup, oRoot As IXMLDOMNode) As Boolean
    If Not (oRoot.nodeType = NODE_ELEMENT) Then
        '/ not an element node so we just skip out
        XMLProperties = True
        Exit Function
    End If
    
    If StrComp(oRoot.nodeName, "properties", vbTextCompare) <> 0 Then
        Exit Function
    End If
    Dim oNode As IXMLDOMNode
    Dim strGroupName As String
    strGroupName = GetNodeAttr(oRoot, "name")
    'Debug.Print "Loading Group", strGroupName
    Dim oProperties As Properties
    
    If oPropertyGroup.Exists(strGroupName) Then
        Set oProperties = oPropertyGroup(strGroupName)
    Else
        Set oProperties = oPropertyGroup.Add(strGroupName)
    End If
    For Each oNode In oRoot.childNodes
        If Not XMLProperty(oProperties, oNode) Then
            Exit Function
        End If
    Next
    XMLProperties = True
End Function

Private Function XMLProperty(oProperties As Properties, oRoot As IXMLDOMNode) As Boolean
    
    If Not (oRoot.nodeType = NODE_ELEMENT) Then
        '/ not an element node so we just skip out
        XMLProperty = True
        Exit Function
    End If
    
    
    If StrComp(oRoot.nodeName, "property", vbTextCompare) <> 0 Then
        Exit Function
    End If
    
    Dim oProp As Property
    If oProperties.Exists(GetNodeAttr(oRoot, "name")) Then
        Set oProp = oProperties(GetNodeAttr(oRoot, "name"))
        oProp.Value = GetNodeAttr(oRoot, "value")
    Else
        Set oProp = oProperties.Add(GetNodeAttr(oRoot, "name"), GetNodeAttr(oRoot, "value"), StringToPropType(GetNodeAttr(oRoot, "type")))
    End If
    oProp.Locked = LenientBool(GetNodeAttr(oRoot, "locked"))
    'Debug.Print "Loaded Property", oProp.Name
    XMLProperty = True
End Function


